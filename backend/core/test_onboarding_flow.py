import hashlib
from datetime import timedelta
from importlib import import_module
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.apps import apps
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from .models import AccountInvitation, Property, Tenant, TenantInvitation, Unit, User, TenancyEvent
from .supabase_auth import SupabaseAuthentication


class OnboardingFlowTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username='manager', email='manager@flow.test', role='manager')
        self.admin = User.objects.create_user(username='admin', email='admin@flow.test', role='admin')
        self.client = APIClient()
        self.client.force_authenticate(self.manager)
        self.prop = Property.objects.create(name='Court', location='Town', owner=self.manager, total_units=1)
        self.unit = Unit.objects.create(property=self.prop, unit_number='1', unit_type='House', rent='20000')
        self.details = {'name': 'Tenant One', 'phone': '+254712345678', 'lease_end': '2027-12-31', 'rent': '20000', 'notes': 'Keys handed over'}
        self.checkin_url = f'/api/properties/{self.prop.pk}/units/{self.unit.pk}/check-in/'

    def check_in(self):
        response = self.client.post(self.checkin_url, self.details, format='multipart')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def invite_account(self, role='staff', email='new@flow.test'):
        response = self.client.post('/api/account-invitations/', {'name': 'New Person', 'email': email, 'role': role, 'phone': '+254700000002'}, format='json')
        return response

    def test_property_creation_generates_only_vacant_houses(self):
        response = self.client.post('/api/properties/', {'name': 'New Court', 'location': 'Town', 'total_units': 4, 'occupied_units': 4, 'status': 'leased', 'monthly_rent': '15000'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        prop = Property.objects.get(pk=response.data['id'])
        self.assertEqual(prop.units.count(), 4)
        self.assertEqual(prop.units.filter(status='vacant', tenant='', rent='15000').count(), 4)
        self.assertEqual(prop.occupied_units, 0)
        self.assertEqual(prop.status, 'vacant')

    def test_checkin_updates_all_records_and_invite_reuses_one_token(self):
        tenant = self.check_in()
        self.unit.refresh_from_db()
        self.prop.refresh_from_db()
        self.assertEqual(self.unit.status, 'occupied')
        self.assertEqual(self.unit.tenant, self.details['name'])
        self.assertEqual(self.prop.occupied_units, 1)
        self.assertEqual(self.prop.status, 'leased')
        self.assertEqual(TenancyEvent.objects.get(tenant_id=tenant['id']).notes, 'Keys handed over')
        self.assertTrue(tenant['can_invite'])
        url = f"/api/tenants/{tenant['id']}/invite/"
        first = self.client.post(url, {'email': 'tenant@flow.test'}, format='json')
        second = self.client.post(url, {'email': 'tenant@flow.test'}, format='json')
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 201, second.data)
        self.assertEqual(first.data['token'], second.data['token'])
        self.assertEqual(TenantInvitation.objects.count(), 1)
        self.assertEqual(self.client.post(self.checkin_url, self.details, format='multipart').status_code, 409)
        self.assertEqual(Tenant.objects.count(), 1)

    def test_invitation_blocked_before_checkin_and_after_checkout(self):
        tenant = Tenant.objects.create(property=self.prop, unit=self.unit, name='Pending', phone='0700', lease_end='2027-12-31', rent='20000', status='pending')
        self.assertEqual(self.client.post(f'/api/tenants/{tenant.pk}/invite/', {'email': 'tenant@flow.test'}, format='json').status_code, 400)
        tenant.delete()
        data = self.check_in()
        invitation = self.client.post(f"/api/tenants/{data['id']}/invite/", {'email': 'tenant@flow.test'}, format='json')
        out = self.client.post('/api/tenancy-events/', {'tenant': data['id'], 'unit': self.unit.pk, 'action': 'check_out'}, format='json')
        self.assertEqual(out.status_code, 201, out.data)
        self.assertEqual(self.client.get(f"/api/tenant-invitations/{invitation.data['token']}/").status_code, 404)

    def test_bad_handover_photo_does_not_create_tenant_or_occupy_house(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        response = self.client.post(self.checkin_url, {**self.details, 'evidence_upload': SimpleUploadedFile('bad.png', b'not a photo')}, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Tenant.objects.exists())
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, 'vacant')

    def test_valid_handover_photo_is_saved_with_checkin(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            photo = SimpleUploadedFile('handover.png', b'\x89PNG\r\n\x1a\n'+b'\x00'*8, content_type='image/png')
            response = self.client.post(self.checkin_url, {**self.details, 'evidence_upload': photo}, format='multipart')
            self.assertEqual(response.status_code, 201, response.data)
            self.assertTrue(TenancyEvent.objects.get().evidence_photo)

    def test_foreign_property_and_unauthorized_roles_cannot_checkin(self):
        other = User.objects.create_user(username='other', email='other@flow.test', role='manager')
        for actor in [other, self.admin]:
            self.client.force_authenticate(actor)
            self.assertIn(self.client.post(self.checkin_url, self.details, format='multipart').status_code, [403,404])
        self.assertFalse(Tenant.objects.exists())

    def test_account_invitation_role_scope_and_reusable_token(self):
        self.assertEqual(self.invite_account(role='manager').status_code, 403)
        first = self.invite_account()
        second = self.invite_account()
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data['token'], second.data['token'])
        self.assertEqual(AccountInvitation.objects.count(), 1)
        invitation = AccountInvitation.objects.get()
        self.assertNotEqual(invitation.token_digest, first.data['token'])
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.invite_account(role='maintenance', email='maintenance@flow.test').status_code, 403)
        manager = self.invite_account(role='manager', email='landlord@flow.test')
        self.assertEqual(manager.status_code, 201, manager.data)
        public = APIClient()
        details = public.get(f"/api/account-invitations/{manager.data['token']}/")
        self.assertEqual(details.status_code, 200)
        self.assertEqual(details.data['role'], 'manager')

    def test_accept_invitation_uses_database_role_and_is_one_time(self):
        response = self.invite_account()
        self.assertEqual(response.status_code, 201, response.data)
        subject = uuid4()
        metadata = {'consent': True, 'role': 'admin', 'account_invitation_token': response.data['token']}
        user = SupabaseAuthentication().provision(subject, 'new@flow.test', metadata)
        self.assertEqual(user.role, 'staff')
        self.assertEqual(user.onboarded_by_id, self.manager.pk)
        self.assertEqual(user.supabase_user_id, subject)
        self.assertFalse(user.has_usable_password())
        with self.assertRaises(AuthenticationFailed):
            SupabaseAuthentication().provision(uuid4(), 'new@flow.test', metadata)
        self.assertEqual(APIClient().get(f"/api/account-invitations/{response.data['token']}/").status_code, 404)

    def test_manager_invite_registration_needs_no_manual_role_change(self):
        self.client.force_authenticate(self.admin)
        response = self.invite_account(role='manager', email='landlord@flow.test')
        self.assertEqual(response.status_code, 201, response.data)
        user = SupabaseAuthentication().provision(uuid4(), 'landlord@flow.test', {'consent': True, 'account_invitation_token': response.data['token']})
        self.assertEqual(user.role, 'manager')

    def test_wrong_email_expired_or_disabled_issuer_cannot_accept(self):
        response = self.invite_account()
        metadata = {'consent': True, 'account_invitation_token': response.data['token']}
        with self.assertRaises(AuthenticationFailed):
            SupabaseAuthentication().provision(uuid4(), 'wrong@flow.test', metadata)
        self.manager.is_active_user = False
        self.manager.save()
        with self.assertRaises(AuthenticationFailed):
            SupabaseAuthentication().provision(uuid4(), 'new@flow.test', metadata)
        self.manager.is_active_user = True
        self.manager.save()
        AccountInvitation.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        with self.assertRaises(AuthenticationFailed):
            SupabaseAuthentication().provision(uuid4(), 'new@flow.test', metadata)

    def test_backfill_preserves_existing_units_and_occupied_status(self):
        self.unit.status = 'occupied'
        self.unit.tenant = 'Existing tenant'
        self.unit.save()
        self.prop.total_units = 3
        self.prop.save()
        migration = import_module('core.migrations.0018_create_missing_property_houses')
        from types import SimpleNamespace
        migration.create_missing_houses(apps, SimpleNamespace(connection=connection))
        self.assertEqual(self.prop.units.count(), 3)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.tenant, 'Existing tenant')
        self.assertEqual(self.unit.status, 'occupied')
        self.assertEqual(self.prop.units.filter(status='vacant').count(), 2)
