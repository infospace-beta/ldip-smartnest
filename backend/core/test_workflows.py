from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .models import User, Property, Unit, Tenant, Notice, MaintenanceJob, MaintenanceOffer, UnitInspection, WorkflowPolicy
from .workflow_service import notify, submit_request, process_automations, create_inspection


class WorkflowTests(TestCase):
    def setUp(self):
        self.manager=User.objects.create_user(username='manager',email='m@sn.test',role='manager')
        WorkflowPolicy.objects.filter(manager=self.manager).update(enabled=True)
        self.other=User.objects.create_user(username='other',email='o@sn.test',role='manager')
        self.admin=User.objects.create_user(username='admin',email='a@sn.test',role='admin')
        self.user=User.objects.create_user(username='tenant',email='t@sn.test',role='tenant',portal_access_granted=True)
        self.provider=User.objects.create_user(username='provider',email='p@sn.test',role='maintenance',onboarded_by=self.manager)
        self.provider2=User.objects.create_user(username='provider2',email='p2@sn.test',role='maintenance',onboarded_by=self.manager)
        self.prop=Property.objects.create(name='Home',owner=self.manager)
        self.unit=Unit.objects.create(property=self.prop,unit_number='1',unit_type='one',rent='100',status='occupied')
        self.tenant=Tenant.objects.create(user=self.user,name='Tenant',phone='0700',property=self.prop,unit=self.unit,lease_end=timezone.localdate()+timedelta(days=365),rent='100')
        self.client=APIClient()
    def as_user(self,user):self.client.force_authenticate(user)
    def test_notice_encryption_and_recipient_scope(self):
        n=notify([self.user],'Private title','Secret leak',important=True,sender=self.manager)
        self.assertEqual(n.text,'');self.assertNotIn('Secret',n.encrypted_content)
        self.as_user(self.other);self.assertEqual(self.client.get('/api/notices/').json(),[])
        self.as_user(self.admin);data=self.client.get('/api/notices/').json()[0]
        self.assertTrue(data['protected']);self.assertNotIn('Secret',str(data));self.assertIn('ciphertext',data)
        self.assertEqual(self.client.post(f'/api/notices/{n.pk}/read/').status_code,404)
        self.as_user(self.user);self.assertEqual(self.client.get('/api/notices/').json()[0]['text'],'Secret leak')
        self.client.post(f'/api/notices/{n.pk}/read/');self.assertEqual(self.client.get('/api/notices/unread-count/').json()['unread_count'],0)
        own=notify([self.admin],'Personal','Admin message')
        self.as_user(self.admin);self.assertFalse(next(x for x in self.client.get('/api/notices/').json() if x['id']==own.pk)['protected'])
    def test_maintenance_lifecycle_and_duplicate(self):
        self.as_user(self.user)
        r=self.client.post('/api/maintenance/',{'issue':'Tap leaking','category':'general','priority':'high'})
        self.assertEqual(r.status_code,201,r.data);pk=r.data['id']
        self.assertEqual(self.client.post('/api/maintenance/',{'issue':'Tap leaking'}).status_code,200)
        self.as_user(self.other);self.assertEqual(self.client.post(f'/api/maintenance/{pk}/approve/').status_code,404)
        self.as_user(self.manager);r=self.client.post(f'/api/maintenance/{pk}/approve/');self.assertEqual(r.status_code,200,r.data)
        job=MaintenanceJob.objects.get(pk=pk);self.assertEqual(job.assigned_to,self.provider)
        self.assertEqual(set(job.conversation.participants.values_list('id',flat=True)),{self.user.pk,self.provider.pk})
        self.as_user(self.provider)
        r=self.client.post(f'/api/maintenance/{pk}/actions/accept/',{'visit_at':(timezone.now()+timedelta(days=1)).isoformat()});self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(self.client.patch(f'/api/maintenance/{pk}/',{'status':'completed'}).status_code,400)
        r=self.client.post(f'/api/maintenance/{pk}/actions/complete/',{'completion_notes':'Tap repaired'});self.assertEqual(r.data['status'],'awaiting_confirmation')
        self.as_user(self.user);r=self.client.post(f'/api/maintenance/{pk}/actions/confirm/');self.assertEqual(r.data['status'],'completed')
    def test_timeout_and_disable_controls(self):
        job,_=submit_request(self.tenant,issue='Broken lock')
        self.as_user(self.manager);self.client.post(f'/api/maintenance/{job.pk}/approve/')
        MaintenanceOffer.objects.filter(job=job).update(expires_at=timezone.now()-timedelta(seconds=1))
        policy=WorkflowPolicy.objects.get(manager=self.manager);policy.enabled=False;policy.save()
        process_automations();job.refresh_from_db();self.assertEqual(job.assigned_to,self.provider)
        policy.enabled=True;policy.save();process_automations();job.refresh_from_db();self.assertEqual(job.assigned_to,self.provider2)
        self.assertNotIn(self.provider,job.conversation.participants.all())
    def test_auto_approval_uses_manager_estimate(self):
        p=WorkflowPolicy.objects.get(manager=self.manager);p.auto_approve=True;p.spending_limit=Decimal('100');p.category_costs={'general':50};p.save()
        job,_=submit_request(self.tenant,issue='Routine fix');self.assertEqual(job.status,'assigned')
        job,_=submit_request(self.tenant,issue='Needs quote',requires_quotation=True);self.assertEqual(job.status,'pending_approval')
    def test_inspection_notice_review_and_separate_charge(self):
        i=create_inspection(self.tenant,'move_in',force=True)
        self.assertGreaterEqual(i.scheduled_at,timezone.now()+timedelta(days=14)-timedelta(minutes=1))
        self.as_user(self.other);self.assertEqual(self.client.get(f'/api/unit-inspections/{i.pk}/').status_code,404)
        self.as_user(self.user);self.assertEqual(self.client.post(f'/api/unit-inspections/{i.pk}/actions/confirm/').status_code,200)
        self.as_user(self.manager)
        r=self.client.post(f'/api/unit-inspections/{i.pk}/actions/complete/',{'checklist':{'rooms':'good','meter_readings':'123'},'issues_found':'Leaking tap'},format='json');self.assertEqual(r.status_code,200,r.data)
        self.client.post(f'/api/unit-inspections/{i.pk}/actions/publish/')
        self.as_user(self.user);r=self.client.post(f'/api/unit-inspections/{i.pk}/actions/review/',{'agrees':False,'comments':'Meter differs'},format='json')
        self.assertEqual(r.data['status'],'closed');self.assertFalse(r.data['agrees_with_report']);self.assertIsNotNone(r.data['acknowledged_at'])
        out=create_inspection(self.tenant,'move_out',force=True);self.assertEqual(out.check_in,i)
        self.as_user(self.manager);r=self.client.post(f'/api/unit-inspections/{out.pk}/actions/charge/',{'proposed_charge':'50','comments':'Review damage'})
        self.assertEqual(r.status_code,200,r.data)
        self.as_user(self.user);r=self.client.post(f'/api/unit-inspections/{out.pk}/actions/charge-response/',{'response':'disputed','comments':'Pre-existing'})
        self.assertEqual(r.data['charge_response'],'disputed');self.assertIsNone(r.data['acknowledged_at'])
    def test_manual_inspection_works_when_automations_off(self):
        p=WorkflowPolicy.objects.get(manager=self.manager);p.enabled=False;p.save()
        self.assertIsNone(create_inspection(self.tenant))
        self.as_user(self.manager);r=self.client.post('/api/unit-inspections/',{'tenant':self.tenant.pk,'inspection_type':'routine'})
        self.assertEqual(r.status_code,201,r.data)

    def test_moveout_creates_inspection_only_when_enabled(self):
        self.as_user(self.manager)
        date=(timezone.now()+timedelta(days=30)).isoformat()
        r=self.client.post(f'/api/tenants/{self.tenant.pk}/move-out/',{'move_out_at':date})
        self.assertEqual(r.status_code,200,r.data);self.assertEqual(r.data['inspection']['inspection_type'],'move_out')
        self.assertGreaterEqual(r.data['inspection']['scheduled_at'],timezone.datetime.fromisoformat(date))
        self.as_user(self.other);self.assertEqual(self.client.post(f'/api/tenants/{self.tenant.pk}/move-out/',{'move_out_at':date}).status_code,404)

    def test_former_tenant_can_review_only_own_reports(self):
        i=create_inspection(self.tenant,force=True)
        self.user.portal_access_granted=False;self.user.save()
        self.as_user(self.user)
        self.assertEqual(self.client.get(f'/api/unit-inspections/{i.pk}/').status_code,200)
        self.assertEqual(self.client.post('/api/maintenance/',{'issue':'New request'}).status_code,401)

    def test_routine_worker_is_idempotent_and_sends_notice(self):
        p=WorkflowPolicy.objects.get(manager=self.manager);p.routine_sample_size=1;p.save()
        process_automations();self.assertEqual(UnitInspection.objects.filter(tenant=self.tenant).count(),1)
        process_automations();self.assertEqual(UnitInspection.objects.filter(tenant=self.tenant).count(),1)
        self.assertTrue(Notice.objects.filter(recipients=self.user).exists())

    def test_notice_model_encrypts_other_writer_paths(self):
        n=Notice.objects.create(title='Protected',text='Private body')
        n.refresh_from_db();self.assertEqual(n.title,'');self.assertEqual(n.text,'');self.assertTrue(n.encrypted_content)

    def test_manager_mfa_is_enforced_by_server(self):
        import base64,json
        from uuid import uuid4
        from django.test import override_settings
        self.manager.supabase_user_id=uuid4();self.manager.mfa_enabled=True;self.manager.save()
        def token(aal,subject=None):
            data=base64.urlsafe_b64encode(json.dumps({'sub':str(subject or self.manager.supabase_user_id),'aal':aal}).encode()).decode().rstrip('=')
            return f'verified-by-authentication.{data}.signature'
        with override_settings(SUPABASE_AUTH_ENABLED=True):
            self.client.force_authenticate(self.manager,token('aal1'))
            self.assertTrue(self.client.get('/api/auth/me/').data['requires_mfa'])
            self.assertEqual(self.client.get('/api/workflow-policy/').status_code,403)
            self.client.force_authenticate(self.manager,token('aal2',uuid4()))
            self.assertEqual(self.client.get('/api/workflow-policy/').status_code,403)
            self.client.force_authenticate(self.manager,token('aal2'))
            self.assertFalse(self.client.get('/api/auth/me/').data['requires_mfa'])
            self.assertEqual(self.client.get('/api/workflow-policy/').status_code,200)

    def test_invalid_policy_cannot_escape_portfolio(self):
        self.as_user(self.manager)
        r=self.client.patch('/api/workflow-policy/',{'inspector':self.other.pk},format='json');self.assertEqual(r.status_code,400)
        r=self.client.patch('/api/workflow-policy/',{'category_costs':{'general':'NaN'}},format='json');self.assertEqual(r.status_code,400)
        r=self.client.patch('/api/workflow-policy/',{'provider_categories':{str(self.other.pk):['plumbing']}},format='json');self.assertEqual(r.status_code,400)

    def test_manager_can_manually_reoffer_when_automations_are_off(self):
        job,_=submit_request(self.tenant,issue='Manual reoffer')
        self.as_user(self.manager);self.client.post(f'/api/maintenance/{job.pk}/approve/')
        WorkflowPolicy.objects.filter(manager=self.manager).update(enabled=False)
        self.as_user(self.provider);self.client.post(f'/api/maintenance/{job.pk}/actions/decline/')
        self.as_user(self.manager)
        r=self.client.post(f'/api/maintenance/{job.pk}/actions/reassign/',{'assigned_to':self.provider.pk})
        self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(MaintenanceOffer.objects.get(job=job,provider=self.provider).status,'pending')
