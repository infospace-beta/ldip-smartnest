import base64
from datetime import timedelta
import io
import json
import re
from unittest.mock import patch
from urllib.error import URLError
from uuid import uuid4
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from .models import User, Notice, SMSNotification
from .sms import deliver_notifications


@override_settings(SUPABASE_AUTH_ENABLED=True, EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AccountSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='manager', email='manager@example.test', role='manager', supabase_user_id=uuid4())
        self.client = APIClient()
        self.authenticate('aal1')

    def authenticate(self, aal, user=None, subject=None):
        user = user or self.user
        payload = base64.urlsafe_b64encode(json.dumps({'sub':str(subject or user.supabase_user_id), 'aal':aal}).encode()).decode().rstrip('=')
        self.client.force_authenticate(user, f'provider-verified.{payload}.signature')

    def post(self, **data):
        return self.client.post('/api/auth/security/', data, format='json')

    def test_manager_enters_workspace_without_mfa_by_default(self):
        self.assertFalse(self.client.get('/api/auth/me/').data['requires_mfa'])
        self.assertEqual(self.client.get('/api/workflow-policy/').status_code, 200)

    def test_admin_also_has_no_forced_mfa(self):
        self.user.role='admin'; self.user.save()
        self.assertFalse(self.client.get('/api/auth/me/').data['requires_mfa'])
        self.assertEqual(self.client.get('/api/users/').status_code, 200)

    def test_all_roles_can_get_and_dismiss_security_recommendation(self):
        for role in ['admin','manager','staff','tenant','maintenance']:
            self.user.role = role; self.user.save()
            self.assertEqual(self.client.get('/api/auth/security/').status_code, 200)
            self.assertEqual(self.post(action='dismiss_recommendation').status_code, 200)

    def test_enabling_needs_current_verified_second_factor_and_matching_subject(self):
        self.assertEqual(self.post(action='enable_mfa').status_code, 403)
        self.authenticate('aal2', subject=uuid4())
        self.assertEqual(self.post(action='enable_mfa').status_code, 403)
        self.authenticate('aal2')
        self.assertTrue(self.post(action='enable_mfa').data['mfa_enabled'])
        self.user.refresh_from_db(); self.authenticate('aal1')
        self.assertTrue(self.client.get('/api/auth/me/').data['requires_mfa'])
        self.assertEqual(self.client.get('/api/workflow-policy/').status_code, 403)
        self.assertEqual(self.post(action='disable_mfa').status_code, 403)
        self.authenticate('aal2')
        self.assertFalse(self.post(action='disable_mfa').data['mfa_enabled'])

    def test_non_manager_opt_in_also_enforces_mfa(self):
        self.user.role='staff'; self.user.mfa_enabled=True; self.user.save()
        self.assertEqual(self.client.get('/api/notices/').status_code, 403)
        self.authenticate('aal2')
        self.assertEqual(self.client.get('/api/notices/').status_code, 200)

    def test_secondary_email_is_verified_once_without_changing_signin_identity(self):
        result = self.post(action='request_secondary_email', email='backup@example.test')
        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.data['secondary_email_verified'])
        code = re.search(r'\b(\d{6})\b', mail.outbox[0].body).group(1)
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.secondary_code_digest, code)
        result = self.post(action='confirm_secondary_email', code=code)
        self.assertTrue(result.data['secondary_email_verified'])
        self.assertEqual(result.data['secondary_email'], 'backup@example.test')
        self.assertEqual(self.post(action='confirm_secondary_email', code=code).status_code, 400)
        self.user.refresh_from_db(); self.assertEqual(self.user.email, 'manager@example.test')
        self.assertNotIn('secondary_email', self.client.get('/api/auth/me/').data)

    def test_secondary_email_attempts_and_expiry_are_enforced(self):
        self.post(action='request_secondary_email', email='backup@example.test')
        code = re.search(r'\b(\d{6})\b', mail.outbox[0].body).group(1)
        wrong = '999999' if code != '999999' else '000000'
        for _ in range(5): self.assertEqual(self.post(action='confirm_secondary_email', code=wrong).status_code, 400)
        self.assertEqual(self.post(action='confirm_secondary_email', code=code).status_code, 400)
        self.user.refresh_from_db(); self.user.secondary_code_attempts=0; self.user.secondary_code_expires_at=timezone.now()-timedelta(seconds=1); self.user.save()
        self.assertEqual(self.post(action='confirm_secondary_email', code=code).status_code, 400)

    def test_duplicate_primary_email_and_unconfigured_delivery_are_rejected(self):
        self.assertEqual(self.post(action='request_secondary_email', email='MANAGER@example.test').status_code, 400)
        with override_settings(EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend'):
            self.assertEqual(self.post(action='request_secondary_email', email='backup@example.test').status_code, 503)
        self.assertEqual(len(mail.outbox), 0)

    def test_failed_email_delivery_does_not_save_pending_address(self):
        with patch('core.account_security.send_mail', side_effect=OSError('unavailable')):
            self.assertEqual(self.post(action='request_secondary_email', email='backup@example.test').status_code, 503)
        self.user.refresh_from_db(); self.assertEqual(self.user.pending_secondary_email, '')

    def test_anonymous_and_disabled_users_cannot_change_settings(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/auth/security/').status_code, 401)
        self.user.is_active_user=False; self.user.save(); self.authenticate('aal2')
        self.assertEqual(self.post(action='dismiss_recommendation').status_code, 401)

    @override_settings(SMARTNEST_SMS_ENABLED=True)
    def test_sms_opt_in_requires_provider_verified_phone(self):
        with patch('core.sms.verified_phone', return_value=''):
            self.assertEqual(self.post(action='sms_notifications', enabled=True).status_code, 400)
        with patch('core.sms.verified_phone', return_value='+254712345678'):
            self.assertEqual(self.post(action='sms_notifications', enabled=True).status_code, 200)
        self.user.refresh_from_db(); self.assertEqual(self.user.sms_verified_phone, '+254712345678')


@override_settings(SMARTNEST_SMS_ENABLED=True, TWILIO_ACCOUNT_SID='ACtest', TWILIO_AUTH_TOKEN='test', TWILIO_MESSAGING_SERVICE_SID='MGtest')
class NotificationSMSTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user(username='sms', email='sms@example.test', role='staff', sms_notifications=True, sms_verified_phone='+254712345678')
        self.notice=Notice.objects.create(title='Private title', text='Private payment amount')

    def queue(self):
        self.notice.recipients.add(self.user)
        return SMSNotification.objects.get()

    def test_queue_is_unique_and_requires_opt_in(self):
        self.queue(); self.notice.recipients.remove(self.user); self.notice.recipients.add(self.user)
        self.assertEqual(SMSNotification.objects.count(),1)
        self.user.sms_notifications=False; self.user.save()
        other=Notice.objects.create(title='Other',text='Other'); other.recipients.add(self.user)
        self.assertEqual(SMSNotification.objects.count(),1)

    def test_dry_run_never_sends(self):
        item=self.queue()
        with patch('core.sms.urlopen') as remote:
            self.assertEqual(deliver_notifications(dry_run=True)['pending'],1)
            remote.assert_not_called()
        item.refresh_from_db(); self.assertEqual(item.status,'pending')

    def test_successful_submission_is_private_and_not_repeated(self):
        item=self.queue()
        with patch('core.sms.urlopen',return_value=io.BytesIO(b'{"sid":"SMtest"}')) as remote:
            self.assertEqual(deliver_notifications()['accepted'],1)
            self.assertNotIn('Private',remote.call_args.args[0].data.decode())
        with patch('core.sms.urlopen') as remote:
            deliver_notifications(); remote.assert_not_called()
        item.refresh_from_db(); self.assertEqual(item.status,'accepted')

    def test_ambiguous_network_failure_is_not_retried(self):
        item=self.queue()
        with patch('core.sms.urlopen',side_effect=URLError('timeout')):
            self.assertEqual(deliver_notifications()['unknown'],1)
        with patch('core.sms.urlopen') as remote:
            deliver_notifications(); remote.assert_not_called()
        item.refresh_from_db(); self.assertEqual(item.status,'unknown')

    def test_opt_out_cancels_pending_delivery(self):
        self.queue(); self.user.sms_notifications=False; self.user.save()
        with patch('core.sms.urlopen') as remote:
            self.assertEqual(deliver_notifications()['skipped'],1); remote.assert_not_called()
