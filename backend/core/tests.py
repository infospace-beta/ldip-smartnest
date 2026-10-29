import re
import tempfile
from urllib.parse import urlparse, parse_qs

from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.test import APIClient

from .models import MaintenanceJob, Payment, Property, Tenant, TenantInvitation, Unit, User


class TenantAccessTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant_user = User.objects.create_user(
            username='jane',
            email='jane@example.com',
            password='secure-password',
            role='tenant',
            portal_access_granted=True,
        )
        self.property = Property.objects.create(name='Green Court', location='Nairobi')
        self.unit = Unit.objects.create(
            property=self.property,
            unit_number='A-1',
            unit_type='One bedroom',
            rent='24000',
            status='occupied',
        )
        self.tenant = Tenant.objects.create(
            user=self.tenant_user,
            name='Jane Doe',
            phone='0712345678',
            property=self.property,
            unit=self.unit,
            lease_end='2027-01-31',
            rent='24000',
        )
        self.other_property = Property.objects.create(name='Blue Court', location='Nairobi')
        self.other_unit = Unit.objects.create(
            property=self.other_property,
            unit_number='B-1',
            unit_type='Studio',
            rent='18000',
            status='occupied',
        )
        self.other_tenant = Tenant.objects.create(
            name='John Doe',
            phone='0798765432',
            property=self.other_property,
            unit=self.other_unit,
            lease_end='2027-01-31',
            rent='18000',
        )
        self.client.force_authenticate(user=self.tenant_user)

    def test_tenant_lists_only_their_records(self):
        Payment.objects.create(
            reference='OWN-001',
            tenant=self.tenant,
            date='2026-01-01',
            amount='24000.00',
            method='mpesa',
        )
        Payment.objects.create(
            reference='OTHER-001',
            tenant=self.other_tenant,
            date='2026-01-01',
            amount='18000.00',
            method='mpesa',
        )
        MaintenanceJob.objects.create(
            job_id='OWN-REQ-1',
            property=self.property,
            unit=self.unit,
            issue='Leaking tap',
            reported_by=self.tenant.name,
            reported_by_user=self.tenant_user,
            assignee='Property management',
            date='2026-01-01',
        )
        MaintenanceJob.objects.create(
            job_id='OTHER-REQ-1',
            property=self.other_property,
            unit=self.other_unit,
            issue='Broken window',
            reported_by=self.other_tenant.name,
            assignee='Property management',
            date='2026-01-01',
        )

        for path, expected_field, expected_value in (
            ('/api/properties/', 'name', 'Green Court'),
            ('/api/units/', 'unit_number', 'A-1'),
            ('/api/tenants/', 'name', 'Jane Doe'),
            ('/api/payments/', 'reference', 'OWN-001'),
            ('/api/maintenance/', 'job_id', 'OWN-REQ-1'),
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.data), 1)
                self.assertEqual(response.data[0][expected_field], expected_value)

    def test_tenant_maintenance_request_uses_linked_unit(self):
        response = self.client.post(
            '/api/maintenance/',
            {'issue': 'Kitchen tap is leaking', 'property': self.other_property.id, 'unit': self.other_unit.id},
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        job = MaintenanceJob.objects.get(job_id=response.data['job_id'])
        self.assertEqual(job.property_id, self.property.id)
        self.assertEqual(job.unit_id, self.unit.id)
        self.assertEqual(job.reported_by_user_id, self.tenant_user.id)

    def test_check_in_and_check_out_are_manager_only_and_revoke_access(self):
        manager = User.objects.create_user(
            username='manager',
            email='manager@example.com',
            password='secure-password',
            role='manager',
        )
        self.property.owner = manager
        self.property.save(update_fields=['owner'])
        self.unit.status = 'vacant'
        self.unit.save(update_fields=['status'])
        self.tenant.status = 'pending'
        self.tenant.save(update_fields=['status'])
        self.client.force_authenticate(user=manager)

        check_in = self.client.post(
            '/api/tenancy-events/',
            {'tenant': self.tenant.id, 'unit': self.unit.id, 'action': 'check_in', 'notes': 'Keys handed over'},
            format='json',
        )
        self.assertEqual(check_in.status_code, 201)
        self.unit.refresh_from_db()
        self.tenant.refresh_from_db()
        self.tenant_user.refresh_from_db()
        self.assertEqual(self.unit.status, 'occupied')
        self.assertEqual(self.tenant.status, 'active')
        self.assertTrue(self.tenant_user.portal_access_granted)

        check_out = self.client.post(
            '/api/tenancy-events/',
            {'tenant': self.tenant.id, 'unit': self.unit.id, 'action': 'check_out'},
            format='json',
        )
        self.assertEqual(check_out.status_code, 201)
        self.unit.refresh_from_db()
        self.tenant.refresh_from_db()
        self.tenant_user.refresh_from_db()
        self.assertEqual(self.unit.status, 'vacant')
        self.assertEqual(self.tenant.status, 'pending')
        self.assertFalse(self.tenant_user.portal_access_granted)
        self.assertEqual(
            self.client.post(
                '/api/tenancy-events/',
                {'tenant': self.tenant.id, 'unit': self.unit.id, 'action': 'check_out'},
                format='json',
            ).status_code,
            400,
        )

    def test_staff_records_are_limited_to_assigned_units(self):
        staff_user = User.objects.create_user(
            username='staff',
            email='staff@example.com',
            password='secure-password',
            role='staff',
        )
        staff_user.assigned_units.add(self.unit)
        self.client.force_authenticate(user=staff_user)

        properties = self.client.get('/api/properties/')
        units = self.client.get('/api/units/')
        tenants = self.client.get('/api/tenants/')
        self.assertEqual(properties.status_code, 200)
        self.assertEqual(properties.data[0]['total_units'], 1)
        self.assertEqual([item['unit_number'] for item in units.data], ['A-1'])
        self.assertEqual([item['name'] for item in tenants.data], ['Jane Doe'])
        created_job = self.client.post(
            '/api/maintenance/',
            {
                'job_id': 'STAFF-WO-1',
                'property': self.property.id,
                'unit': self.unit.id,
                'issue': 'Replace the kitchen tap',
                'priority': 'medium',
                'reported_by': 'Agency staff',
                'assignee': 'Maintenance vendor',
                'status': 'logged',
                'date': '2026-01-02',
            },
            format='json',
        )
        self.assertEqual(created_job.status_code, 201, created_job.data)

    def test_manager_sees_only_owned_property_records(self):
        manager = User.objects.create_user(
            username='owner-manager',
            email='owner@example.com',
            password='secure-password',
            role='manager',
        )
        other_manager = User.objects.create_user(
            username='other-manager',
            email='other-manager@example.com',
            password='secure-password',
            role='manager',
        )
        self.property.owner = manager
        self.property.save(update_fields=['owner'])
        self.other_property.owner = other_manager
        self.other_property.save(update_fields=['owner'])
        client = APIClient()
        client.force_authenticate(user=manager)

        self.assertEqual([row['name'] for row in client.get('/api/properties/').data], ['Green Court'])
        self.assertEqual([row['name'] for row in client.get('/api/tenants/').data], ['Jane Doe'])
        self.assertEqual(
            client.get(f'/api/properties/{self.other_property.id}/').status_code,
            404,
        )
        denied_unit = client.post(
            '/api/units/',
            {
                'property': self.other_property.id,
                'unit_number': 'A-9',
                'unit_type': 'Studio',
                'rent': '10000',
            },
            format='json',
        )
        self.assertEqual(denied_unit.status_code, 403)
        job = MaintenanceJob.objects.create(
            job_id='OWNED-WO-1',
            property=self.property,
            unit=self.unit,
            issue='Leaking tap',
            reported_by='Tenant',
            assignee='Maintenance vendor',
            date='2026-01-02',
        )
        denied_reassignment = client.patch(
            f'/api/maintenance/{job.id}/',
            {'property': self.other_property.id, 'unit': self.other_unit.id},
            format='json',
        )
        self.assertEqual(denied_reassignment.status_code, 403)

    def test_check_in_photo_is_saved_and_only_available_to_authorized_property_users(self):
        manager = User.objects.create_user(
            username='photo-manager',
            email='photo-manager@example.com',
            password='secure-password',
            role='manager',
        )
        self.property.owner = manager
        self.property.save(update_fields=['owner'])
        self.unit.status = 'vacant'
        self.unit.save(update_fields=['status'])
        self.tenant.status = 'pending'
        self.tenant.save(update_fields=['status'])
        image = SimpleUploadedFile(
            'handover.png',
            b'\x89PNG\r\n\x1a\n' + b'\x00' * 12,
            content_type='image/png',
        )
        client = APIClient()
        client.force_authenticate(user=manager)
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = client.post(
                    '/api/tenancy-events/',
                    {
                        'tenant': self.tenant.id,
                        'unit': self.unit.id,
                        'action': 'check_in',
                        'evidence_upload': image,
                    },
                    format='multipart',
                )
                self.assertEqual(response.status_code, 201, response.data)
                self.assertTrue(response.data['evidence_photo'])
                photo = client.get(f"/api/tenancy-events/{response.data['id']}/photo/")
                self.assertEqual(photo.status_code, 200)
                self.assertIn(b'\x89PNG', b''.join(photo.streaming_content))

                other_manager = User.objects.create_user(
                    username='unrelated-manager',
                    email='unrelated-manager@example.com',
                    password='secure-password',
                    role='manager',
                )
                client.force_authenticate(user=other_manager)
                self.assertEqual(
                    client.get(f"/api/tenancy-events/{response.data['id']}/photo/").status_code,
                    404,
                )


class MaintenanceVendorTests(TestCase):
    def test_vendor_updates_only_assigned_work_orders_and_needs_photo_to_complete(self):
        client = APIClient()
        vendor = User.objects.create_user(
            username='vendor',
            email='vendor@example.com',
            password='secure-password',
            role='maintenance',
        )
        property_record = Property.objects.create(name='Green Court', location='Nairobi')
        unit = Unit.objects.create(
            property=property_record,
            unit_number='A-1',
            unit_type='Studio',
            rent='18000',
        )
        job = MaintenanceJob.objects.create(
            job_id='WO-001',
            property=property_record,
            unit=unit,
            issue='Leaking pipe',
            reported_by='Manager',
            assignee=vendor.email,
            status='logged',
            date='2026-01-01',
        )
        other_job = MaintenanceJob.objects.create(
            job_id='WO-002',
            property=property_record,
            unit=unit,
            issue='Broken light',
            reported_by='Manager',
            assignee='someone-else@example.com',
            status='logged',
            date='2026-01-01',
        )
        client.force_authenticate(user=vendor)

        jobs = client.get('/api/maintenance/')
        self.assertEqual([item['job_id'] for item in jobs.data], ['WO-001'])
        denied = client.patch(
            f'/api/maintenance/{other_job.id}/',
            {'status': 'in_progress'},
            format='json',
        )
        self.assertEqual(denied.status_code, 404)

        started = client.patch(
            f'/api/maintenance/{job.id}/',
            {'status': 'in_progress', 'quote_amount': '1250.00', 'quote_notes': 'Replace the valve'},
            format='json',
        )
        self.assertEqual(started.status_code, 200, started.data)
        self.assertEqual(started.data['status'], 'in_progress')
        self.assertEqual(str(started.data['quote_amount']), '1250.00')

        no_photo = client.patch(
            f'/api/maintenance/{job.id}/',
            {'status': 'completed'},
            format='json',
        )
        self.assertEqual(no_photo.status_code, 400)
        completed = client.patch(
            f'/api/maintenance/{job.id}/',
            {'status': 'completed', 'confirmation_photo_url': 'https://example.com/finished.jpg'},
            format='json',
        )
        self.assertEqual(completed.status_code, 200, completed.data)
        self.assertEqual(completed.data['status'], 'completed')


class TenantRegistrationTests(TestCase):
    def test_public_registration_requires_consent_and_tenant_role(self):
        client = APIClient()
        registration = {
            'username': 'newtenant',
            'email': 'newtenant@example.com',
            'password': 'secure-password',
            'role': 'tenant',
            'phone': '0700000000',
        }

        missing_consent = client.post('/api/auth/register/', registration, format='json')
        self.assertEqual(missing_consent.status_code, 400)

        disallowed_role = client.post(
            '/api/auth/register/',
            {**registration, 'email': 'manager@example.com', 'role': 'manager', 'consent': True},
            format='json',
        )
        self.assertEqual(disallowed_role.status_code, 400)
        self.assertFalse(User.objects.filter(email='manager@example.com').exists())

        valid_registration = client.post(
            '/api/auth/register/',
            {**registration, 'consent': True},
            format='json',
        )
        self.assertEqual(valid_registration.status_code, 201)
        user = User.objects.get(email='newtenant@example.com')
        self.assertIsNotNone(user.registration_consent_at)
        self.assertFalse(user.portal_access_granted)
        self.assertNotIn('tokens', valid_registration.data)
        self.assertEqual(
            client.post(
                '/api/auth/login/',
                {'email': 'newtenant@example.com', 'password': 'secure-password'},
                format='json',
            ).status_code,
            400,
        )

        manager = User.objects.create_user(
            username='manager',
            email='manager@example.com',
            password='secure-password',
            role='manager',
        )
        property_record = Property.objects.create(name='Green Court', location='Nairobi', owner=manager)
        unit = Unit.objects.create(
            property=property_record,
            unit_number='A-2',
            unit_type='Studio',
            rent='20000',
        )
        client.force_authenticate(user=manager)
        linked = client.post(
            '/api/tenants/',
            {
                'name': 'New Tenant',
                'phone': '0700000000',
                'account_email': 'newtenant@example.com',
                'property': property_record.id,
                'unit': unit.id,
                'lease_end': '2027-01-31',
                'rent': '20000',
                'status': 'pending',
            },
            format='json',
        )
        self.assertEqual(linked.status_code, 201, linked.data)
        user.refresh_from_db()
        self.assertTrue(user.portal_access_granted)
        self.assertEqual(
            client.post(
                '/api/auth/login/',
                {'email': 'newtenant@example.com', 'password': 'secure-password'},
                format='json',
            ).status_code,
            200,
        )

    def test_manager_can_invite_tenant_to_create_and_link_account(self):
        manager = User.objects.create_user(
            username='invite-manager',
            email='invite-manager@example.com',
            password='secure-password',
            role='manager',
        )
        property_record = Property.objects.create(name='Invite Court', location='Nairobi')
        property_record.owner = manager
        property_record.save(update_fields=['owner'])
        unit = Unit.objects.create(
            property=property_record,
            unit_number='B-1',
            unit_type='Studio',
            rent='20000',
        )
        client = APIClient()
        client.force_authenticate(user=manager)
        tenant_response = client.post(
            '/api/tenants/',
            {
                'name': 'Invited Tenant',
                'phone': '0700000000',
                'property': property_record.id,
                'unit': unit.id,
                'lease_end': '2027-01-31',
                'rent': '20000',
                'status': 'pending',
            },
            format='json',
        )
        self.assertEqual(tenant_response.status_code, 201, tenant_response.data)

        invitation_response = client.post(
            f"/api/tenants/{tenant_response.data['id']}/invite/",
            {'email': 'invited@example.com'},
            format='json',
        )
        self.assertEqual(invitation_response.status_code, 201, invitation_response.data)
        token = invitation_response.data['token']
        invitation = TenantInvitation.objects.get(tenant_id=tenant_response.data['id'])
        self.assertNotEqual(invitation.token_digest, token)
        staff_user = User.objects.create_user(
            username='invite-staff',
            email='invite-staff@example.com',
            password='secure-password',
            role='staff',
        )
        client.force_authenticate(user=staff_user)
        self.assertEqual(
            client.post(
                f"/api/tenants/{tenant_response.data['id']}/invite/",
                {'email': 'another@example.com'},
                format='json',
            ).status_code,
            403,
        )
        client.force_authenticate(user=manager)

        details = client.get(f'/api/tenant-invitations/{token}/')
        self.assertEqual(details.status_code, 200)
        self.assertEqual(details.data['email'], 'invited@example.com')
        mismatched_email = client.post(
            '/api/auth/register/',
            {
                'email': 'different@example.com',
                'username': 'Not.Invited',
                'password': 'secure-password',
                'role': 'tenant',
                'consent': True,
                'invitation_token': token,
            },
            format='json',
        )
        self.assertEqual(mismatched_email.status_code, 400)

        registration = client.post(
            '/api/auth/register/',
            {
                'email': 'invited@example.com',
                'username': 'Invited.Tenant',
                'password': 'secure-password',
                'phone': '0700000000',
                'role': 'tenant',
                'consent': True,
                'invitation_token': token,
            },
            format='json',
        )
        self.assertEqual(registration.status_code, 201, registration.data)
        user = User.objects.get(email='invited@example.com')
        self.assertTrue(user.portal_access_granted)
        self.assertEqual(Tenant.objects.get(pk=tenant_response.data['id']).user_id, user.id)
        self.assertEqual(
            client.post(
                '/api/auth/login/',
                {'email': user.email, 'password': 'secure-password'},
                format='json',
            ).status_code,
            200,
        )
        self.assertEqual(client.get(f'/api/tenant-invitations/{token}/').status_code, 404)


class RoleAndCommunicationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='secure-password',
            role='admin',
        )
        self.manager = User.objects.create_user(
            username='manager',
            email='manager@example.com',
            password='secure-password',
            role='manager',
        )
        self.tenant = User.objects.create_user(
            username='tenant',
            email='tenant@example.com',
            password='secure-password',
            role='tenant',
            portal_access_granted=True,
        )
        self.property = Property.objects.create(name='Green Court', location='Nairobi')
        self.property.owner = self.manager
        self.property.save(update_fields=['owner'])
        self.unit = Unit.objects.create(
            property=self.property,
            unit_number='A-1',
            unit_type='Studio',
            rent='18000',
        )
        Tenant.objects.create(
            user=self.tenant,
            name='Tenant User',
            phone='0711111111',
            property=self.property,
            unit=self.unit,
            lease_end='2027-01-31',
            rent='18000',
        )

    def test_only_admin_can_grant_manager_role_and_admin_cannot_read_financials(self):
        self.client.force_authenticate(user=self.manager)
        denied = self.client.patch(
            f'/api/users/{self.tenant.id}/',
            {'role': 'manager'},
            format='json',
        )
        self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(user=self.admin)
        granted = self.client.patch(
            f'/api/users/{self.tenant.id}/',
            {'role': 'manager'},
            format='json',
        )
        self.assertEqual(granted.status_code, 200)
        self.assertEqual(granted.data['role'], 'manager')
        rejected_legacy_role = self.client.patch(
            f'/api/users/{self.tenant.id}/',
            {'role': 'landlord'},
            format='json',
        )
        self.assertEqual(rejected_legacy_role.status_code, 400)
        self.assertEqual(self.client.get('/api/properties/').status_code, 403)
        self.assertEqual(self.client.get('/api/payments/').status_code, 403)
        self.assertEqual(self.client.get('/api/expenses/').status_code, 403)

    def test_conversations_are_visible_only_to_participants(self):
        self.client.force_authenticate(user=self.manager)
        started = self.client.post(
            '/api/communication/conversations/',
            {'recipient': self.tenant.id, 'subject': 'Welcome', 'body': 'Your account is ready.'},
            format='json',
        )
        self.assertEqual(started.status_code, 201)
        conversation_id = started.data['id']

        other_user = User.objects.create_user(
            username='other',
            email='other@example.com',
            password='secure-password',
            role='manager',
        )
        self.client.force_authenticate(user=other_user)
        self.assertEqual(self.client.get('/api/communication/conversations/').data, [])
        self.assertEqual(
            self.client.get(f'/api/communication/conversations/{conversation_id}/messages/').status_code,
            404,
        )

    def test_admin_can_assign_properties_and_managers_see_only_their_own(self):
        other_manager = User.objects.create_user(
            username='other-manager',
            email='other-manager@example.com',
            password='secure-password',
            role='manager',
        )
        other_property = Property.objects.create(
            name='Blue Court',
            location='Nairobi',
            owner=other_manager,
        )
        self.client.force_authenticate(user=self.admin)
        assigned = self.client.patch(
            f'/api/users/{self.manager.id}/',
            {'managed_properties': [self.property.id]},
            format='json',
        )
        self.assertEqual(assigned.status_code, 200, assigned.data)
        self.assertEqual(assigned.data['managed_property_ids'], [self.property.id])
        self.assertEqual(self.client.get('/api/properties/').status_code, 403)

        self.client.force_authenticate(user=self.manager)
        visible = self.client.get('/api/properties/')
        self.assertEqual(visible.status_code, 200)
        self.assertEqual([item['name'] for item in visible.data], ['Green Court'])
        self.assertEqual(
            self.client.get(f'/api/properties/{other_property.id}/').status_code,
            404,
        )
        self.assertEqual(self.client.get('/api/users/').status_code, 403)

    def test_manager_can_onboard_staff_and_maintenance_only(self):
        self.client.force_authenticate(user=self.manager)
        staff_response = self.client.post(
            '/api/team/onboarding/',
            {
                'username': 'new-staff',
                'email': 'new-staff@example.com',
                'password': 'Staff-password-2',
                'role': 'staff',
                'assigned_units': [self.unit.id],
            },
            format='json',
        )
        self.assertEqual(staff_response.status_code, 201, staff_response.data)
        staff_user = User.objects.get(email='new-staff@example.com')
        self.assertEqual(staff_user.role, 'staff')
        self.assertTrue(staff_user.check_password('Staff-password-2'))
        self.assertEqual(list(staff_user.assigned_units.values_list('id', flat=True)), [self.unit.id])

        maintenance_response = self.client.post(
            '/api/team/onboarding/',
            {
                'username': 'new-maintenance',
                'email': 'new-maintenance@example.com',
                'password': 'Crew-password-2',
                'role': 'maintenance',
            },
            format='json',
        )
        self.assertEqual(maintenance_response.status_code, 201, maintenance_response.data)
        self.assertEqual(
            User.objects.get(email='new-maintenance@example.com').role,
            'maintenance',
        )

        denied_role = self.client.post(
            '/api/team/onboarding/',
            {
                'username': 'new-admin',
                'email': 'new-admin@example.com',
                'password': 'Admin-password-2',
                'role': 'admin',
            },
            format='json',
        )
        self.assertEqual(denied_role.status_code, 400)
        self.client.force_authenticate(user=self.tenant)
        self.assertEqual(
            self.client.post('/api/team/onboarding/', {}, format='json').status_code,
            403,
        )

        self.client.force_authenticate(user=self.admin)
        self.assertEqual(self.client.get('/api/communication/conversations/').data, [])


class AccountSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox = []
        self.user = User.objects.create_user(
            username='account-holder',
            email='account-holder@example.com',
            password='Original-password-1',
            role='manager',
        )
        self.client = APIClient()

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        FRONTEND_URL='https://smartnest.test',
    )
    def test_password_reset_email_uses_generic_response_and_resets_password(self):
        old_access = str(RefreshToken.for_user(self.user).access_token)
        unknown = self.client.post(
            '/api/auth/password/reset/',
            {'email': 'nobody@example.com'},
            format='json',
        )
        requested = self.client.post(
            '/api/auth/password/reset/',
            {'email': self.user.email},
            format='json',
        )
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(requested.status_code, 200)
        self.assertEqual(unknown.data['message'], requested.data['message'])
        self.assertEqual(len(mail.outbox), 1)

        reset_url = re.search(r'https://smartnest\.test/reset-password\?[^\s]+', mail.outbox[0].body)
        self.assertIsNotNone(reset_url)
        query = parse_qs(urlparse(reset_url.group(0)).query)
        response = self.client.post(
            '/api/auth/password/reset/confirm/',
            {
                'uid': query['uid'][0],
                'token': query['token'][0],
                'new_password': 'New-secure-password-2',
                'confirm_password': 'New-secure-password-2',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('New-secure-password-2'))
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {old_access}')
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 401)

    def test_authenticated_password_change_checks_current_password_and_revokes_old_token(self):
        access = str(RefreshToken.for_user(self.user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        denied = self.client.post(
            '/api/auth/password/change/',
            {
                'current_password': 'wrong-password',
                'new_password': 'Another-secure-password-3',
                'confirm_password': 'Another-secure-password-3',
            },
            format='json',
        )
        self.assertEqual(denied.status_code, 400)
        changed = self.client.post(
            '/api/auth/password/change/',
            {
                'current_password': 'Original-password-1',
                'new_password': 'Another-secure-password-3',
                'confirm_password': 'Another-secure-password-3',
            },
            format='json',
        )
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 401)
