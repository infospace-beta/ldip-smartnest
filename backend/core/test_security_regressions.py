import os
from pathlib import Path
import subprocess
import sys

import jwt
from django.conf import settings
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from .models import MaintenanceJob, Property, Tenant, Unit, User
from .views import can_contact, can_view_user


class MaintenanceAuthorizationTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username='manager', email='manager@example.com', role='manager',
        )
        self.vendor = User.objects.create_user(
            username='vendor', email='vendor@example.com', role='maintenance',
        )
        self.attacker = User.objects.create_user(
            username='attacker', email='attacker@example.com', role='maintenance',
        )
        self.staff = User.objects.create_user(
            username='staff', email='staff@example.com', role='staff', onboarded_by=self.manager,
        )
        self.property = Property.objects.create(name='Own', owner=self.manager)
        self.unit = Unit.objects.create(property=self.property, unit_number='1')
        self.foreign_property = Property.objects.create(name='Foreign')
        self.foreign_unit = Unit.objects.create(property=self.foreign_property, unit_number='2')
        self.tenant_user = User.objects.create_user(
            username='tenant', email='tenant@example.com', role='tenant', portal_access_granted=True,
        )
        self.tenant = Tenant.objects.create(
            user=self.tenant_user, name='Tenant', property=self.property,
            unit=self.unit, lease_end='2027-01-01', rent='1000',
        )
        self.job = MaintenanceJob.objects.create(
            job_id='SEC-1', property=self.property, unit=self.unit, issue='Repair',
            reported_by='Tenant', reported_by_user=self.tenant_user,
            assigned_to=self.vendor, assignee=self.vendor.email,
            status='assigned', date='2026-01-01',
        )
        self.client = APIClient()

    def test_matching_email_and_legacy_label_grant_no_job_or_contact_access(self):
        self.client.force_authenticate(self.attacker)
        for label in (self.vendor.email, 'released-vendor-name'):
            self.job.assignee = label
            self.job.save(update_fields=['assignee'])
            renamed = self.client.patch('/api/auth/me/', {'username': label}, format='json')
            self.assertEqual(renamed.status_code, 200, renamed.data)
            self.attacker.refresh_from_db()
            self.assertEqual(self.client.get('/api/maintenance/').data, [])
            for suffix in ('', 'photo/'):
                self.assertEqual(self.client.get(f'/api/maintenance/{self.job.pk}/{suffix}').status_code, 404)
            self.assertEqual(self.client.patch(
                f'/api/maintenance/{self.job.pk}/', {'status': 'in_progress'}, format='json',
            ).status_code, 404)
            for other in (self.manager, self.staff, self.tenant_user):
                self.assertFalse(can_contact(self.attacker, other))
                self.assertFalse(can_contact(other, self.attacker))
                self.assertFalse(can_view_user(self.attacker, other))
            self.assertEqual(self.client.post('/api/communication/conversations/', {
                'recipient': self.tenant_user.pk, 'subject': 'Claimed job', 'body': 'Hello',
            }, format='json').status_code, 403)

    def test_onboarding_shared_label_does_not_reveal_pending_requests(self):
        self.job.assigned_to = None
        self.job.assignee = 'Property management'
        self.job.status = 'pending_approval'
        self.job.save()
        self.client.force_authenticate(self.manager)
        created = self.client.post('/api/team/onboarding/', {
            'username': 'Property management', 'email': 'shared@example.com',
            'password': 'Testing-password-123', 'role': 'maintenance',
        }, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.client.force_authenticate(User.objects.get(email='shared@example.com'))
        self.assertEqual(self.client.get('/api/maintenance/').data, [])
        self.assertEqual(self.client.get(f'/api/maintenance/{self.job.pk}/photo/').status_code, 404)

    def test_explicit_assignment_survives_rename_and_preserves_updates_and_contacts(self):
        self.vendor.username = 'renamed-provider'
        self.vendor.save(update_fields=['username'])
        self.client.force_authenticate(self.vendor)
        self.assertEqual([job['id'] for job in self.client.get('/api/maintenance/').data], [self.job.pk])
        updated = self.client.patch(f'/api/maintenance/{self.job.pk}/', {
            'status': 'in_progress', 'quote_amount': '100',
        }, format='json')
        self.assertEqual(updated.status_code, 200, updated.data)
        for other in (self.manager, self.staff, self.tenant_user):
            self.assertTrue(can_contact(self.vendor, other))
            self.assertTrue(can_contact(other, self.vendor))

    def test_staff_cannot_rebind_to_foreign_unit_or_remove_unit(self):
        self.client.force_authenticate(self.staff)
        for values in (
            {'property': self.foreign_property.pk, 'unit': self.foreign_unit.pk},
            {'property': self.foreign_property.pk, 'unit': None},
            {'unit': None},
        ):
            response = self.client.patch(f'/api/maintenance/{self.job.pk}/', values, format='json')
            self.assertEqual(response.status_code, 403, response.data)
            self.job.refresh_from_db()
            self.assertEqual(self.job.unit_id, self.unit.pk)
            self.assertEqual(self.job.property_id, self.property.pk)

    def test_explicit_staff_cannot_move_job_to_unassigned_sibling_unit(self):
        self.staff.onboarded_by = None
        self.staff.save(update_fields=['onboarded_by'])
        self.staff.assigned_units.add(self.unit)
        sibling = Unit.objects.create(property=self.property, unit_number='3')
        self.client.force_authenticate(self.staff)
        response = self.client.patch(f'/api/maintenance/{self.job.pk}/', {
            'unit': sibling.pk,
        }, format='json')
        self.assertEqual(response.status_code, 403, response.data)
        self.job.refresh_from_db()
        self.assertEqual(self.job.unit_id, self.unit.pk)

    def test_reassignment_revokes_old_provider_even_with_stale_label(self):
        self.job.assigned_to = self.attacker
        self.job.save(update_fields=['assigned_to'])
        self.client.force_authenticate(self.vendor)
        self.assertEqual(self.client.get('/api/maintenance/').data, [])
        self.assertFalse(can_contact(self.vendor, self.tenant_user))
        self.client.force_authenticate(self.attacker)
        self.assertEqual(self.client.get(f'/api/maintenance/{self.job.pk}/').status_code, 200)

    def test_manager_can_link_manual_and_legacy_orders_to_a_portfolio_provider(self):
        self.client.force_authenticate(self.manager)
        payload = {
            'job_id': 'SEC-MANUAL', 'property': self.property.pk, 'unit': self.unit.pk,
            'issue': 'Manual repair', 'reported_by': 'Manager', 'assignee': 'Service contact',
            'status': 'assigned', 'date': '2026-01-01', 'assigned_to': self.vendor.pk,
        }
        created = self.client.post('/api/maintenance/', payload, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.job.assigned_to = None
        self.job.status = 'logged'
        self.job.save()
        linked = self.client.patch(f'/api/maintenance/{self.job.pk}/', {
            'assigned_to': self.vendor.pk, 'status': 'assigned',
        }, format='json')
        self.assertEqual(linked.status_code, 200, linked.data)
        self.client.force_authenticate(self.vendor)
        self.assertEqual(len(self.client.get('/api/maintenance/').data), 2)

    def test_assignment_rejects_unlinked_accounts_and_non_providers(self):
        self.client.force_authenticate(self.manager)
        for account in (self.attacker, self.staff):
            rejected = self.client.patch(f'/api/maintenance/{self.job.pk}/', {
                'assigned_to': account.pk,
            }, format='json')
            self.assertEqual(rejected.status_code, 400, rejected.data)
            self.job.refresh_from_db()
            self.assertEqual(self.job.assigned_to_id, self.vendor.pk)

    def test_staff_metadata_and_explicit_unit_assignment_updates_still_work(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.patch(f'/api/maintenance/{self.job.pk}/', {
            'issue': 'Updated repair',
        }, format='json').status_code, 200)
        self.staff.assigned_units.add(self.foreign_unit)
        response = self.client.patch(f'/api/maintenance/{self.job.pk}/', {
            'property': self.foreign_property.pk, 'unit': self.foreign_unit.pk,
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)


class SigningConfigurationTests(SimpleTestCase):
    def test_startup_requires_a_private_key_and_preserves_configured_value(self):
        script = 'import smartnest_api.settings as s; import os; assert s.SECRET_KEY == os.environ["DJANGO_SECRET_KEY"]'
        for key in (None, '', ' ' * 60, 'short', 'django-insecure-' + 'x' * 60, 'test-private-key-' + 'x' * 64):
            env = os.environ.copy()
            env.pop('DJANGO_SECRET_KEY', None)
            if key is not None:
                env['DJANGO_SECRET_KEY'] = key
            result = subprocess.run(
                [sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
                env=env, capture_output=True, text=True,
            )
            if key and key.startswith('test-private-key-'):
                self.assertEqual(result.returncode, 0, result.stderr)
            else:
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('ImproperlyConfigured', result.stderr)


class TokenSigningTests(TestCase):
    def test_old_key_cannot_resign_an_issued_token_but_current_tokens_work(self):
        user = User.objects.create_user(
            username='signed-user', email='signed@example.com', role='manager',
            password='Testing-password-123',
        )
        client = APIClient()
        login = client.post('/api/auth/login/', {
            'email': user.email, 'password': 'Testing-password-123',
        }, format='json')
        self.assertEqual(login.status_code, 200, login.data)
        tokens = login.data['tokens']
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {tokens["access"]}')
        self.assertEqual(client.get('/api/auth/me/').status_code, 200)
        old_public_key = 'django-insecure-smartnest-dev-secret-key-change-in-production'
        for name in ('access', 'refresh'):
            payload = jwt.decode(tokens[name], options={'verify_signature': False})
            payload['exp'] += 86400 * 365
            forged = jwt.encode(payload, old_public_key, algorithm='HS256')
            if name == 'access':
                client.credentials(HTTP_AUTHORIZATION=f'Bearer {forged}')
                self.assertEqual(client.get('/api/auth/me/').status_code, 401)
            else:
                client.credentials()
                self.assertEqual(client.post('/api/auth/token/refresh/', {
                    'refresh': forged,
                }, format='json').status_code, 401)
        client.credentials()
        refreshed = client.post('/api/auth/token/refresh/', {'refresh': tokens['refresh']}, format='json')
        self.assertEqual(refreshed.status_code, 200, refreshed.data)
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {refreshed.data["access"]}')
        self.assertEqual(client.get('/api/auth/me/').status_code, 200)
        self.assertNotEqual(settings.SECRET_KEY, old_public_key)
