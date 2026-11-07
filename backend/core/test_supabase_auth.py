import io
import json
from pathlib import Path
import runpy
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from uuid import uuid4

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory

from .models import User
from .supabase_auth import AuthUnavailable, SupabaseAuthentication


class SupabaseURLConfigurationTests(SimpleTestCase):
    @override_settings(SUPABASE_AUTH_ENABLED=True)
    def test_supabase_mode_removes_legacy_credential_endpoints(self):
        backend = Path(__file__).resolve().parent.parent
        root = runpy.run_path(str(backend / 'smartnest_api/urls.py'))['urlpatterns']
        self.assertNotIn('token_refresh', [getattr(pattern, 'name', None) for pattern in root])
        core = runpy.run_path(str(backend / 'core/urls.py'), run_name='core._supabase_urls_test')['urlpatterns']
        names = {pattern.name for pattern in core}
        self.assertIn('me', names)
        self.assertFalse(names & {'register', 'login', 'change_password', 'request_password_reset', 'confirm_password_reset'})


@override_settings(SUPABASE_URL='https://test.supabase.co', SUPABASE_PUBLISHABLE_KEY='sb_publishable_test')
class SupabaseAuthenticationTests(TestCase):
    def setUp(self):
        self.subject = uuid4()
        self.user = User.objects.create_user(
            username='manager', email='manager@example.com', password='old-password',
            role='manager', supabase_user_id=self.subject,
        )
        self.identity = {
            'id': str(self.subject), 'email': self.user.email,
            'email_confirmed_at': timezone.now().isoformat(),
            'user_metadata': {'role': 'admin', 'portal_access_granted': True},
        }
        self.factory = APIRequestFactory()

    def authenticate(self, identity=None):
        response = io.BytesIO(json.dumps(identity or self.identity).encode())
        with patch('core.supabase_auth.urlopen', return_value=response) as remote:
            result = SupabaseAuthentication().authenticate(self.factory.get('/', HTTP_AUTHORIZATION='Bearer test-token'))
            self.assertEqual(remote.call_args.args[0].full_url, 'https://test.supabase.co/auth/v1/user')
            return result

    def test_verified_subject_retains_database_role(self):
        user, token = self.authenticate()
        self.assertEqual(user.pk, self.user.pk)
        self.assertEqual(user.role, 'manager')
        self.assertEqual(token, 'test-token')

    def test_new_identity_cannot_claim_existing_email(self):
        self.identity['id'] = str(uuid4())
        with self.assertRaises(AuthenticationFailed):
            self.authenticate()

    def test_new_signup_requires_a_server_issued_invitation(self):
        self.identity.update(id=str(uuid4()),email='tenant@example.com')
        self.identity['user_metadata']['consent']=True
        with self.assertRaises(AuthenticationFailed):self.authenticate()
        self.assertFalse(User.objects.filter(email='tenant@example.com').exists())

    def test_unconfirmed_email_is_rejected(self):
        self.identity['email_confirmed_at'] = None
        with self.assertRaises(AuthenticationFailed):
            self.authenticate()

    def test_disabled_account_is_rejected(self):
        self.user.is_active_user = False
        self.user.save()
        with self.assertRaises(AuthenticationFailed):
            self.authenticate()

    def test_invalid_remote_token_is_rejected(self):
        with patch('core.supabase_auth.urlopen', side_effect=HTTPError('https://test', 401, 'Invalid JWT', {}, None)):
            with self.assertRaises(AuthenticationFailed):
                SupabaseAuthentication().authenticate(self.factory.get('/', HTTP_AUTHORIZATION='Bearer invalid'))

    def test_provider_outage_fails_closed(self):
        with patch('core.supabase_auth.urlopen', side_effect=URLError('offline')):
            with self.assertRaises(AuthUnavailable):
                SupabaseAuthentication().authenticate(self.factory.get('/', HTTP_AUTHORIZATION='Bearer token'))

    def test_missing_or_malformed_bearer(self):
        auth = SupabaseAuthentication()
        self.assertIsNone(auth.authenticate(self.factory.get('/')))
        with self.assertRaises(AuthenticationFailed):
            auth.authenticate(self.factory.get('/', HTTP_AUTHORIZATION='Bearer token extra'))

    def test_explicit_identity_link_retains_role(self):
        other = User.objects.create_user(username='staff', email='staff@example.com', role='staff')
        subject = uuid4()
        call_command('link_supabase_user', other.email, str(subject), stdout=io.StringIO())
        other.refresh_from_db()
        self.assertEqual(other.supabase_user_id, subject)
        self.assertEqual(other.role, 'staff')
