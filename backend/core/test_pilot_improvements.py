from datetime import timedelta
from unittest import skipUnless
from django.db import connection, transaction, DatabaseError
from django.db.models.deletion import ProtectedError
from django.test import TestCase, SimpleTestCase
from django.utils import timezone
from . import test_workflows
from .models import MaintenanceJob, TenancyEvent, User, Property, Unit, Tenant, UnitInspection


class PilotWorkflowTests(TestCase):
    def setUp(self):
        test_workflows.WorkflowTests.setUp(self)

    def job(self, key, **changes):
        values = dict(job_id=key, property=self.prop, unit=self.unit, issue='Tap repair', date=timezone.localdate(), reported_by='Resident', reported_by_user=self.user, assignee='Provider', assigned_to=self.provider, status='pending_approval')
        values.update(changes)
        return MaintenanceJob.objects.create(**values)

    def test_task_inbox_scopes_manager_provider_tenant_and_staff(self):
        self.job('LOCAL-PENDING')
        self.job('LOCAL-LATE', status='in_progress', due_at=timezone.now()-timedelta(days=1))
        foreign = Property.objects.create(owner=self.other, name='Foreign home')
        self.job('FOREIGN', property=foreign, unit=None, reported_by_user=None, assigned_to=self.provider2)
        staff = User.objects.create_user(username='staff',email='staff@pilot.test',role='staff',onboarded_by=self.manager)
        for user, approvals, late in [(self.manager,1,1),(self.other,1,0),(self.provider,0,1),(self.user,0,1),(staff,0,1)]:
            self.client.force_authenticate(user)
            response = self.client.get('/api/dashboard/tasks/')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.data['counts'].get('approvals',0),approvals)
            self.assertEqual(response.data['counts'].get('overdue_repairs',0),late)
            self.assertEqual(response['Cache-Control'],'private, no-store')
            if user!=self.other:self.assertNotIn('Foreign home',str(response.data))

    def test_upcoming_inspections_are_limited_to_own_home(self):
        UnitInspection.objects.create(tenant=self.tenant,unit=self.unit,inspector_name='Inspector',inspection_date=timezone.localdate()+timedelta(days=2),scheduled_at=timezone.now()+timedelta(days=2),status='awaiting_confirmation')
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get('/api/dashboard/tasks/').data['counts']['upcoming_inspections'],1)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get('/api/dashboard/tasks/').data['counts']['upcoming_inspections'],0)

    def test_admin_inbox_contains_no_property_operations(self):
        self.job('PRIVATE-REPAIR')
        self.client.force_authenticate(self.admin)
        response=self.client.get('/api/dashboard/tasks/')
        self.assertEqual(response.status_code,200)
        self.assertNotIn('Tap repair',str(response.data))
        self.assertNotIn('overdue_repairs',response.data['counts'])

    def test_tenancy_and_handover_deletion_is_blocked(self):
        event=TenancyEvent.objects.create(tenant=self.tenant,unit=self.unit,recorded_by=self.manager,action='check_in')
        for item in [self.tenant,event,self.prop,self.unit,self.user]:
            with self.assertRaises(ProtectedError),transaction.atomic():item.delete()
        with self.assertRaises(ProtectedError),transaction.atomic():Tenant.objects.filter(pk=self.tenant.pk).delete()
        self.assertTrue(Tenant.objects.filter(pk=self.tenant.pk).exists())
        self.assertTrue(TenancyEvent.objects.filter(pk=event.pk).exists())

    def test_property_delete_returns_retention_guidance_and_moveout_keeps_history(self):
        self.client.force_authenticate(self.manager)
        response=self.client.delete(f'/api/properties/{self.prop.pk}/')
        self.assertEqual(response.status_code,409)
        response=self.client.post('/api/tenancy-events/',{'tenant':self.tenant.pk,'unit':self.unit.pk,'action':'check_out'},format='json')
        self.assertEqual(response.status_code,201,response.data)
        self.assertTrue(Tenant.objects.filter(pk=self.tenant.pk).exists())
        self.assertTrue(TenancyEvent.objects.filter(tenant=self.tenant,action='check_out').exists())

    @skipUnless(connection.vendor=='postgresql','PostgreSQL history guards')
    def test_raw_delete_and_truncate_cannot_bypass_retention(self):
        for command in ['DELETE FROM tenants WHERE id=%s','TRUNCATE tenants CASCADE']:
            with self.assertRaises(DatabaseError),transaction.atomic():
                with connection.cursor() as cursor:cursor.execute(command,[self.tenant.pk] if '%s' in command else None)
        self.assertTrue(Tenant.objects.filter(pk=self.tenant.pk).exists())


    @skipUnless(connection.vendor=='postgresql','PostgreSQL coordinated backup locks')
    def test_backup_blocks_mutations_and_keeps_reads_available(self):
        import psycopg2
        from .backup_lock import LOCK_ID
        with psycopg2.connect(**connection.get_connection_params()) as backup:
            try:
                with backup.cursor() as cursor:
                    cursor.execute('SELECT pg_advisory_lock(%s)', [LOCK_ID])
                self.client.force_authenticate(self.manager)
                response=self.client.post('/api/properties/', {'name':'Do not create during backup'}, format='json')
                self.assertEqual(response.status_code,503)
                self.assertEqual(response['Retry-After'],'30')
                self.assertFalse(Property.objects.filter(name='Do not create during backup').exists())
                self.assertEqual(self.client.get('/api/dashboard/tasks/').status_code,200)
            finally:
                with backup.cursor() as cursor:cursor.execute('SELECT pg_advisory_unlock(%s)', [LOCK_ID])


class PrivateStorageContractTests(SimpleTestCase):
    def test_media_does_not_produce_download_urls(self):
        from .private_storage import PrivateMediaStorage
        storage=PrivateMediaStorage(access_key='server-only-test',secret_key='server-only-test',bucket_name='private-test',region_name='ap-south-1')
        with self.assertRaisesMessage(ValueError,'authorized SmartNest API'):storage.url('profile-photos/private.jpg')

    def test_profile_upload_does_not_serialize_storage_urls(self):
        from .serializers import UserProfileSerializer
        self.assertTrue(UserProfileSerializer().fields['avatar_image'].write_only)
