from django.test import TestCase
from rest_framework.test import APIClient
from core.models import User


class PendingAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='waiting', email='waiting@example.invalid', role='tenant')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_pending_tenant_can_read_own_profile_only(self):
        response = self.client.get('/api/auth/me/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['email'], self.user.email)
        self.assertFalse(response.data['portal_access_granted'])
        for path in ['/api/properties/', '/api/tenants/', '/api/payments/', '/api/maintenance/', '/api/users/']:
            with self.subTest(path=path):
                self.assertIn(self.client.get(path).status_code, (401, 403))

    def test_pending_tenant_cannot_edit_profile(self):
        self.assertIn(self.client.patch('/api/auth/me/', {'username': 'changed'}, format='json').status_code, (401, 403))

    def test_disabled_profile_is_denied(self):
        self.user.is_active_user = False
        self.user.save()
        self.assertIn(self.client.get('/api/auth/me/').status_code, (401, 403))

    def test_anonymous_profile_is_denied(self):
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get('/api/auth/me/').status_code, (401, 403))
