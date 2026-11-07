from datetime import timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4
import os
import subprocess
import sys

from django.core.management import call_command, CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone
from PIL import Image
from io import BytesIO
from rest_framework.test import APIClient
from . import test_workflows
from .models import Tenant, User, Unit, TenantInvitation, Notice, WorkflowPolicy
from .serializers import TenantSerializer, UserAccessSerializer, validate_image_upload
from .workflow_service import create_inspection, process_automations
from .workflow_crypto import seal, unseal


class HardeningTests(TestCase):
    def setUp(self):
        test_workflows.WorkflowTests.setUp(self)

    def test_anonymous_preclaim_and_old_unverified_link_are_rejected(self):
        self.client.force_authenticate(None)
        data = {'email': 'victim@sn.test', 'username': 'attacker', 'password': 'Strong-pass-159!', 'role': 'tenant', 'consent': True}
        for extra in ({}, {'invitation_token': ''}, {'invitation_token': 'not-a-token'}):
            response = self.client.post('/api/auth/register/', {**data, **extra}, format='json')
            self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email=data['email']).exists())
        # Historical pre-claims remain untrusted, even though their row already exists.
        preclaim = User.objects.create_user(email=data['email'], username='old', role='tenant')
        with self.assertRaisesMessage(Exception, 'not accepted a verified invitation'):
            TenantSerializer().validate_account_email(preclaim.email.upper())

    def test_returning_verified_account_keeps_history_and_restores_access(self):
        self.user.supabase_user_id = uuid4(); self.user.save()
        self.client.force_authenticate(self.manager)
        out = self.client.post('/api/tenancy-events/', {'tenant': self.tenant.pk, 'unit': self.unit.pk, 'action': 'check_out'}, format='json')
        self.assertEqual(out.status_code, 201, out.data)
        response = self.client.post(f'/api/properties/{self.prop.pk}/units/{self.unit.pk}/check-in/', {
            'name': 'Returning tenant', 'phone': '0700', 'lease_end': '2028-01-01', 'rent': '100', 'account_email': self.user.email,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data['account_linked'])
        self.assertEqual(Tenant.objects.filter(user=self.user).count(), 2)
        self.tenant.refresh_from_db();self.user.refresh_from_db()
        self.assertEqual(self.tenant.status, 'pending')
        self.assertTrue(self.user.portal_access_granted)
        from .views import tenant_record
        self.assertEqual(tenant_record(self.user).pk, response.data['id'])
        self.assertTrue(self.tenant.events.filter(action='check_out').exists())

    def test_active_tenant_cannot_be_attached_twice(self):
        self.user.supabase_user_id=uuid4();self.user.save()
        with self.assertRaisesMessage(Exception, 'active tenancy'):
            TenantSerializer().validate_account_email(self.user.email)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Tenant.objects.create(user=self.user, property=self.prop, name='Duplicate', phone='', lease_end='2028-01-01', rent='100')

    def test_verified_migration_invalidates_old_password_even_in_legacy_mode(self):
        from .serializers import LoginSerializer
        self.user.set_password('Old-attacker-password-1!');self.user.save()
        call_command('link_supabase_user',self.user.email,str(uuid4()),stdout=StringIO())
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())
        self.assertIsNotNone(self.user.identity_verified_at)
        self.assertFalse(LoginSerializer(data={'email':self.user.email,'password':'Old-attacker-password-1!'}).is_valid())
        # A historical UUID link may have left a usable password: login must still fail.
        self.user.set_password('Old-attacker-password-1!');self.user.save()
        self.assertFalse(LoginSerializer(data={'email':self.user.email,'password':'Old-attacker-password-1!'}).is_valid())

    def test_verification_survives_deletion_of_former_property(self):
        self.user.identity_verified_at=timezone.now();self.user.save()
        self.prop.delete()
        self.user.refresh_from_db()
        self.assertEqual(TenantSerializer().validate_account_email(self.user.email),self.user)

    def test_provider_scope_survives_unrelated_update(self):
        self.provider.scope_to_assigned_units=True;self.provider.save()
        self.provider.assigned_units.add(self.unit)
        serializer=UserAccessSerializer(self.provider, data={'is_active_user':False}, partial=True, context={'request':type('Request', (), {'user':self.admin})()})
        self.assertTrue(serializer.is_valid(), serializer.errors);serializer.save()
        self.assertEqual(list(self.provider.assigned_units.all()), [self.unit])

    def test_moveout_change_reschedules_once_and_requests_confirmation(self):
        inspection=create_inspection(self.tenant, 'move_out', force=True)
        inspection.status='scheduled';inspection.reminded_at=timezone.now();inspection.save()
        self.client.force_authenticate(self.manager)
        date=timezone.now()+timedelta(days=40)
        url=f'/api/tenants/{self.tenant.pk}/move-out/'
        response=self.client.post(url, {'move_out_at':date.isoformat()}, format='json')
        self.assertEqual(response.status_code,200,response.data)
        inspection.refresh_from_db();self.assertGreaterEqual(inspection.scheduled_at,date)
        self.assertEqual(inspection.status,'awaiting_confirmation');self.assertIsNone(inspection.reminded_at)
        count=Notice.objects.count()
        self.client.post(url, {'move_out_at':date.isoformat()}, format='json')
        self.assertEqual(Notice.objects.count(),count)

    def test_worker_isolates_policy_failures(self):
        from . import workflow_service
        real=workflow_service._process_policy
        failed=WorkflowPolicy.objects.get(manager=self.manager)
        def action(pk, now):
            if pk==failed.pk: raise RuntimeError('simulated')
            return real(pk,now)
        with patch('core.workflow_service._process_policy', side_effect=action):
            result=process_automations()
        self.assertEqual(result['failures'],1)
        self.assertIsNotNone(WorkflowPolicy.objects.get(manager=self.other).worker_seen_at)

    def test_readiness_checks_database_and_fresh_worker_heartbeat(self):
        with TemporaryDirectory() as directory, override_settings(AUTOMATION_HEARTBEAT_PATH=Path(directory)/'heartbeat'), patch('core.management.commands.process_smartnest_automations.close_old_connections'):
            self.assertEqual(self.client.get('/api/health/ready/').status_code,503)
            call_command('process_smartnest_automations',stdout=StringIO())
            self.assertEqual(self.client.get('/api/health/ready/').status_code,200)
            with patch('core.management.commands.process_smartnest_automations.process_automations', side_effect=RuntimeError('secret')):
                with self.assertRaises(CommandError):call_command('process_smartnest_automations',stdout=StringIO())


class ImageAndKeyTests(SimpleTestCase):
    def test_backup_refuses_missing_media_unless_explicitly_recorded(self):
        from cryptography.fernet import Fernet
        from .recovery import make_backup, restore_backup
        from io import BytesIO
        from zipfile import ZipFile
        import json
        key=Fernet.generate_key()
        def dump(program, arguments, database):
            Path(arguments[arguments.index('--file')+1]).write_bytes(b'synthetic dump')
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory), patch.dict(os.environ, {'SMARTNEST_BACKUP_KEY':key.decode()}), patch('core.recovery.uploaded_names', return_value=['missing.jpg']), patch('core.recovery.pg_run', side_effect=dump):
            # No database is accessed by this focused filesystem/manifest test.
            with override_settings(DATABASES={'default':{'ENGINE':'django.db.backends.postgresql','NAME':'test'}}):
                path=Path(directory)/'snapshot.snbackup'
                with self.assertRaises(CommandError):make_backup(path)
                self.assertFalse(path.exists())
                self.assertEqual(make_backup(path,allow_missing=True),{'included':0,'missing':1})
                with ZipFile(BytesIO(Fernet(key).decrypt(path.read_bytes()))) as archive:
                    self.assertEqual(json.loads(archive.read('manifest.json'))['missing_media'],['missing.jpg'])
            with self.assertRaises(CommandError):restore_backup(path,'not-a-restore-target',Path(directory)/'media',Path(directory)/'secrets')

    def test_image_spoof_and_location_metadata(self):
        with self.assertRaises(Exception):
            validate_image_upload(SimpleUploadedFile('fake.png', b'\x89PNG\r\n\x1a\n'+b'not real'))
        image=Image.new('RGB',(8,8));exif=Image.Exif();exif[270]='private camera metadata'
        original=BytesIO();image.save(original,'JPEG',exif=exif)
        clean=validate_image_upload(SimpleUploadedFile('misleading.html',original.getvalue(),content_type='text/html'))
        self.assertTrue(clean.name.endswith('.jpg'))
        with Image.open(clean) as decoded:
            self.assertFalse(decoded.getexif())

    def test_explicit_key_ring_retains_old_notice_decryption(self):
        import base64,hashlib,hmac
        from django.conf import settings
        from cryptography.fernet import Fernet
        with patch.dict(os.environ, {'NOTICE_ENCRYPTION_KEYS':''}):
            previous=seal('Before rotation','Confidential')
        legacy=base64.urlsafe_b64encode(hmac.new(settings.SECRET_KEY.encode(),b'smartnest-notices-v1',hashlib.sha256).digest()).decode()
        with patch.dict(os.environ, {'NOTICE_ENCRYPTION_KEYS':Fernet.generate_key().decode()+','+legacy}):
            self.assertEqual(unseal(previous)['text'],'Confidential')
            self.assertEqual(unseal(seal('New','Message'))['title'],'New')

    def test_production_defaults_are_secure_and_reject_development_flags(self):
        from cryptography.fernet import Fernet
        env={**os.environ,'DJANGO_ENV':'production','DJANGO_ALLOWED_HOSTS':'api.example.com','NOTICE_ENCRYPTION_KEYS':Fernet.generate_key().decode(),
             'DB_USER':'smartnest_app','DB_PASSWORD':'test-only-not-a-real-password','DJANGO_MEDIA_ROOT':str(Path.cwd()/'private-test-media'),
             'SUPABASE_AUTH_ENABLED':'true','SUPABASE_URL':'https://example.supabase.co','SUPABASE_PUBLISHABLE_KEY':'test-only',
             'FRONTEND_URL':'https://example.com','DJANGO_CORS_ORIGINS':'https://example.com','DJANGO_CSRF_ORIGINS':'https://example.com'}
        env.pop('DEBUG',None)
        result=subprocess.run([sys.executable,'-c','import smartnest_api.settings as s; assert not s.DEBUG; assert s.SECURE_SSL_REDIRECT and s.CSRF_COOKIE_SECURE and s.SESSION_COOKIE_SECURE; assert not s.CORS_ALLOW_ALL_ORIGINS'],env=env,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        for bad in ({'DEBUG':'true'},{'DJANGO_ALLOWED_HOSTS':'*'},{'DB_USER':'postgres'},{'SUPABASE_AUTH_ENABLED':'false'}):
            result=subprocess.run([sys.executable,'-c','import smartnest_api.settings'],env={**env,**bad},capture_output=True)
            self.assertNotEqual(result.returncode,0)
