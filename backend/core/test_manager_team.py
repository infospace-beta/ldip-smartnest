from datetime import timedelta
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import AccountInvitation, Property, User
from .supabase_auth import SupabaseAuthentication


class ManagerTeamTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username='Manager', email='manager@team.test', role='manager')
        self.other = User.objects.create_user(username='Other', email='other@team.test', role='manager')
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def invite(self, email='new@team.test', role='staff'):
        result = self.client.post('/api/account-invitations/', {'name':'New Person', 'email':email, 'phone':'0700123456', 'role':role}, format='json')
        self.assertEqual(result.status_code, 201, result.data)
        return result.data, AccountInvitation.objects.get(email=email)

    def link(self, invitation):
        return self.client.post(f'/api/team/invitations/{invitation.pk}/link/', {}, format='json')

    def test_manager_sees_only_own_accounts_and_outstanding_invitations(self):
        User.objects.create_user(username='Own staff', email='staff@team.test', role='staff', onboarded_by=self.manager)
        User.objects.create_user(username='Own repairs', email='repairs@team.test', role='maintenance', onboarded_by=self.manager, is_active_user=False)
        User.objects.create_user(username='Foreign', email='foreign@team.test', role='staff', onboarded_by=self.other)
        self.invite()
        self.client.force_authenticate(self.other)
        self.invite('other-pending@team.test')
        self.client.force_authenticate(self.manager)
        response = self.client.get('/api/team/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row['email'] for row in response.data}, {'staff@team.test', 'repairs@team.test', 'new@team.test'})
        self.assertEqual({row['status'] for row in response.data}, {'active', 'inactive', 'pending'})
        self.assertNotIn('token', str(response.data))
        self.assertIn('no-store', response['Cache-Control'])

    def test_invitation_remains_visible_as_one_account_after_acceptance(self):
        data, invitation = self.invite(role='maintenance')
        self.assertEqual(self.client.get('/api/team/').data[0]['status'], 'pending')
        user = SupabaseAuthentication().provision(uuid4(), 'new@team.test', {'consent':True, 'account_invitation_token':data['token']})
        rows = self.client.get('/api/team/').data
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'active')
        self.assertEqual(rows[0]['role'], 'maintenance')
        self.assertEqual(user.onboarded_by_id, self.manager.pk)
        self.assertFalse(rows[0]['can_invite'])
        self.assertEqual(self.link(invitation).status_code, 409)

    def test_pending_invitation_reuses_exact_link_without_creating_duplicates(self):
        data, invitation = self.invite()
        response = self.link(invitation)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['token'], data['token'])
        self.assertEqual(self.link(invitation).data['token'], data['token'])
        self.assertEqual(AccountInvitation.objects.count(), 1)
        self.assertEqual(APIClient().get(f"/api/account-invitations/{response.data['token']}/").status_code, 200)

    def test_expired_invitation_can_be_renewed_and_old_link_is_invalid(self):
        data, invitation = self.invite()
        invitation.expires_at = timezone.now() - timedelta(days=1)
        invitation.save(update_fields=['expires_at'])
        self.assertEqual(self.client.get('/api/team/').data[0]['status'], 'expired')
        renewed = self.link(invitation)
        self.assertEqual(renewed.status_code, 200)
        self.assertNotEqual(renewed.data['token'], data['token'])
        self.assertEqual(APIClient().get(f"/api/account-invitations/{data['token']}/").status_code, 404)
        self.assertEqual(APIClient().get(f"/api/account-invitations/{renewed.data['token']}/").status_code, 200)
        self.assertEqual(AccountInvitation.objects.count(), 1)

    def test_other_managers_and_non_managers_cannot_share_team_links(self):
        _, invitation = self.invite()
        self.client.force_authenticate(self.other)
        self.assertEqual(self.link(invitation).status_code, 404)
        for role in ['admin', 'tenant', 'staff', 'maintenance']:
            actor = User.objects.create_user(username=role, email=f'{role}@denied.test', role=role)
            self.client.force_authenticate(actor)
            self.assertIn(self.client.get('/api/team/').status_code, [401,403])
            self.assertIn(self.link(invitation).status_code, [401,403])
        self.client.force_authenticate(None)
        self.assertIn(self.client.get('/api/team/').status_code, [401,403])

    def test_transferred_property_and_existing_accounts_block_reinvitation(self):
        _, invitation = self.invite()
        prop = Property.objects.create(name='Transferred', location='Town', owner=self.other)
        invitation.property = prop
        invitation.save(update_fields=['property'])
        self.assertEqual(self.client.get('/api/team/').data[0]['status'], 'unavailable')
        self.assertIn(self.link(invitation).status_code, [401,403])
        invitation.property = None
        invitation.save(update_fields=['property'])
        User.objects.create_user(username='Existing', email=invitation.email, role='tenant')
        self.assertEqual(self.link(invitation).status_code, 409)
