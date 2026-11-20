import hashlib
import io
import json
from datetime import timedelta
from unittest.mock import patch
from urllib.error import URLError
from uuid import uuid4
from django.core.cache import cache
from django.test import TestCase,override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from .models import User,AccountInvitation


@override_settings(SUPABASE_AUTH_ENABLED=True,SUPABASE_URL='https://test.supabase.co',SUPABASE_PUBLISHABLE_KEY='public-test-key')
class ExistingIdentityInvitationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin=User.objects.create_user(username='admin',email='admin@invite.test',role='admin')
        self.code='server-issued-one-time-code'
        self.invitation=AccountInvitation.objects.create(created_by=self.admin,email='manager@invite.test',name='Manager',role='manager',token_digest=hashlib.sha256(self.code.encode()).hexdigest(),expires_at=timezone.now()+timedelta(days=7))
        self.subject=uuid4()
        self.identity={'id':str(self.subject),'email':'manager@invite.test','email_confirmed_at':timezone.now().isoformat(),
            'user_metadata':{'role':'admin','account_invitation_token':'stale-code','consent':False}}
        self.client=APIClient()

    def accept(self,**extra):
        payload={'account_invitation_token':self.code,'consent':True,**extra}
        with patch('core.supabase_auth.urlopen',return_value=io.BytesIO(json.dumps(self.identity).encode())) as remote:
            response=self.client.post('/api/auth/invitations/accept/',payload,format='json',HTTP_AUTHORIZATION='Bearer provider-verified-token')
            self.assertEqual(remote.call_args.args[0].full_url,'https://test.supabase.co/auth/v1/user')
            return response

    def test_confirmed_existing_provider_account_accepts_database_role(self):
        response=self.accept(role='admin',email='attacker@invite.test')
        self.assertEqual(response.status_code,201,response.data)
        self.assertEqual(response.data['role'],'manager')
        user=User.objects.get(supabase_user_id=self.subject)
        self.assertEqual(user.email,'manager@invite.test')
        self.assertFalse(user.has_usable_password())
        self.invitation.refresh_from_db();self.assertIsNotNone(self.invitation.accepted_at)

    def test_unconfirmed_email_cannot_accept(self):
        self.identity['email_confirmed_at']=None
        self.assertEqual(self.accept().status_code,401)
        self.assertEqual(User.objects.count(),1)

    def test_different_verified_email_cannot_claim_invitation(self):
        self.identity['email']='different@invite.test'
        self.assertEqual(self.accept().status_code,401)
        self.invitation.refresh_from_db();self.assertIsNone(self.invitation.accepted_at)

    def test_expired_or_disabled_issuer_is_rejected(self):
        self.invitation.expires_at=timezone.now()-timedelta(seconds=1);self.invitation.save()
        self.assertEqual(self.accept().status_code,401)
        self.invitation.expires_at=timezone.now()+timedelta(days=1);self.invitation.save()
        self.admin.is_active_user=False;self.admin.save()
        self.assertEqual(self.accept().status_code,401)

    def test_explicit_consent_and_exactly_one_code_are_required(self):
        self.assertEqual(self.accept(consent=False).status_code,400)
        self.assertEqual(self.accept(invitation_token='another-token').status_code,400)
        self.assertEqual(User.objects.count(),1)

    def test_existing_local_account_is_never_promoted(self):
        user=User.objects.create_user(username='staff',email=self.identity['email'],role='staff',supabase_user_id=self.subject)
        self.assertEqual(self.accept().status_code,409)
        user.refresh_from_db();self.assertEqual(user.role,'staff')

    def test_replay_cannot_create_another_account(self):
        self.assertEqual(self.accept().status_code,201)
        self.assertEqual(self.accept().status_code,409)
        self.assertEqual(User.objects.filter(supabase_user_id=self.subject).count(),1)

    def test_missing_bearer_and_provider_outage_fail_closed(self):
        self.assertEqual(self.client.post('/api/auth/invitations/accept/',{},format='json').status_code,401)
        with patch('core.supabase_auth.urlopen',side_effect=URLError('offline')):
            response=self.client.post('/api/auth/invitations/accept/',{'account_invitation_token':self.code,'consent':True},format='json',HTTP_AUTHORIZATION='Bearer test')
        self.assertEqual(response.status_code,503)
        self.assertEqual(User.objects.count(),1)

    def test_tenant_invitation_uses_explicit_code_and_preserves_checkin_requirement(self):
        from .models import Property,Unit,Tenant,TenantInvitation,TenancyEvent
        manager=User.objects.create_user(username='landlord',email='landlord@invite.test',role='manager')
        prop=Property.objects.create(owner=manager,name='Court',location='Town')
        unit=Unit.objects.create(property=prop,unit_number='1',unit_type='House',status='occupied')
        tenant=Tenant.objects.create(property=prop,unit=unit,name='Resident',phone='+254712345678',lease_end=timezone.localdate()+timedelta(days=365),rent='20000')
        invite=TenantInvitation.objects.create(tenant=tenant,created_by=manager,email=self.identity['email'],token_digest=hashlib.sha256(self.code.encode()).hexdigest(),expires_at=timezone.now()+timedelta(days=7))
        payload={'invitation_token':self.code,'consent':True}
        with patch('core.supabase_auth.urlopen',return_value=io.BytesIO(json.dumps(self.identity).encode())):
            self.assertEqual(self.client.post('/api/auth/invitations/accept/',payload,format='json',HTTP_AUTHORIZATION='Bearer verified').status_code,401)
        TenancyEvent.objects.create(tenant=tenant,unit=unit,action='check_in',recorded_by=manager)
        with patch('core.supabase_auth.urlopen',return_value=io.BytesIO(json.dumps(self.identity).encode())):
            response=self.client.post('/api/auth/invitations/accept/',payload,format='json',HTTP_AUTHORIZATION='Bearer verified')
        self.assertEqual(response.status_code,201,response.data)
        self.assertEqual(response.data['role'],'tenant')
        tenant.refresh_from_db();self.assertEqual(tenant.user.supabase_user_id,self.subject)
        invite.refresh_from_db();self.assertIsNotNone(invite.accepted_at)
        self.invitation.refresh_from_db();self.assertIsNone(self.invitation.accepted_at)