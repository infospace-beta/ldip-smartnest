from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from .daraja import DarajaSandbox, DarajaUnavailable
from .models import User, Property, Unit, Tenant, Payment, Notice, WorkflowPolicy, SandboxPaymentAttempt, SMSNotification
from .recovery import stored_upload_names
from .workflow_service import process_automations, notify


class PersistentRecordTests(TestCase):
    def test_old_records_and_uploads_survive_automation_passes(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            manager=User.objects.create_user(username='owner',email='owner@retention.test',role='manager')
            WorkflowPolicy.objects.filter(manager=manager).update(enabled=False)
            user=User.objects.create_user(username='resident',email='resident@retention.test',role='tenant',portal_access_granted=True)
            user.avatar_image.save('retained.jpg',ContentFile(b'old uploaded bytes'))
            prop=Property.objects.create(owner=manager,name='Retained property',location='Nairobi')
            unit=Unit.objects.create(property=prop,unit_number='1',unit_type='Studio',status='occupied')
            tenant=Tenant.objects.create(user=user,property=prop,unit=unit,name='Resident',phone='+254712345678',lease_end=timezone.localdate()-timedelta(days=3000),rent='20000')
            payment=Payment.objects.create(tenant=tenant,reference='OLD-RETAINED',date=timezone.localdate()-timedelta(days=3000),amount=20000,method='cash')
            notice=notify([user],'Old notice','Retained notice')
            old=timezone.now()-timedelta(days=3650)
            for model,pk in [(User,user.pk),(Property,prop.pk),(Tenant,tenant.pk),(Payment,payment.pk),(Notice,notice.pk)]:
                date_field='date_joined' if model is User else 'created_at'
                model.objects.filter(pk=pk).update(**{date_field:old})
            for _ in range(2): process_automations()
            self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())
            self.assertTrue(Tenant.objects.filter(pk=tenant.pk).exists())
            self.assertTrue(Notice.objects.filter(pk=notice.pk).exists())
            self.assertEqual(Path(user.avatar_image.path).read_bytes(),b'old uploaded bytes')
            client=APIClient();client.force_authenticate(manager)
            self.assertEqual(client.get('/api/payments/').data[0]['reference'],'OLD-RETAINED')

    def test_backups_include_unreferenced_uploads_but_never_source_secrets(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            root=Path(directory);(root/'profile-photos/old').mkdir(parents=True)
            (root/'profile-photos/old/preserved.jpg').write_bytes(b'photo')
            (root/'.env').write_text('PRIVATE=do-not-include')
            self.assertEqual(stored_upload_names(),{'profile-photos/old/preserved.jpg'})

    @override_settings(SMARTNEST_SMS_ENABLED=True)
    def test_real_workflow_notice_queues_sms_without_m2m_signal(self):
        user=User.objects.create_user(username='sms',email='sms@retention.test',role='staff',sms_notifications=True,sms_verified_phone='+254712345678')
        notice=notify([user],'Private title','Private body')
        self.assertEqual(SMSNotification.objects.get().notice_id,notice.pk)


@override_settings(DARAJA_SANDBOX_ENABLED=True,DARAJA_ENV='sandbox')
class DarajaSandboxTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner=User.objects.create_user(username='owner',email='owner@mpesa.test',role='manager')
        prop=Property.objects.create(owner=self.owner,name='Test',location='Nairobi')
        unit=Unit.objects.create(property=prop,unit_number='1',unit_type='Studio',status='occupied')
        self.user=User.objects.create_user(username='tenant',email='tenant@mpesa.test',role='tenant',portal_access_granted=True)
        self.tenant=Tenant.objects.create(user=self.user,property=prop,unit=unit,name='Resident',phone='+254712345678',lease_end=timezone.localdate()+timedelta(days=100),rent='20,000')
        self.client=APIClient();self.client.force_authenticate(self.user)
        self.key=str(uuid4())

    def start(self,**data):
        values={'phone':'+254712345678','idempotency_key':self.key,**data}
        return self.client.post('/api/payments/mpesa/',values,format='json')

    def pending(self):
        with patch('core.daraja_views.DarajaSandbox.start',return_value={'ResponseCode':'0','CheckoutRequestID':'checkout','MerchantRequestID':'merchant'}):
            response=self.start()
        self.assertEqual(response.status_code,202,response.data)
        return SandboxPaymentAttempt.objects.get()

    def test_amount_is_server_calculated_and_duplicate_request_sends_only_once(self):
        with patch('core.daraja_views.DarajaSandbox.start',return_value={'ResponseCode':'0','CheckoutRequestID':'checkout','MerchantRequestID':'merchant'}) as remote:
            self.assertEqual(self.start(amount='1').status_code,202)
            self.assertEqual(self.start(amount='999999').status_code,200)
            self.assertEqual(remote.call_count,1)
        attempt=SandboxPaymentAttempt.objects.get()
        self.assertEqual(attempt.amount,Decimal('20000'));self.assertEqual(attempt.phone,'254712345678')
        self.assertEqual(self.start(phone='+254722345678').status_code,409)
        self.assertEqual(Payment.objects.count(),0)

    def test_unconfigured_sandbox_never_contacts_provider(self):
        with override_settings(DARAJA_SANDBOX_ENABLED=False),patch('core.daraja.urlopen') as remote:
            self.assertEqual(self.start().status_code,503);remote.assert_not_called()
        self.assertEqual(SandboxPaymentAttempt.objects.count(),0)

    def test_bad_phone_and_bad_rent_are_rejected(self):
        self.assertEqual(self.start(phone='+12025550123').status_code,400)
        self.tenant.rent='NaN';self.tenant.save()
        with patch('core.daraja_views.DarajaSandbox.start') as remote:
            self.assertEqual(self.start().status_code,400);remote.assert_not_called()

    def test_callbacks_are_correlated_idempotent_and_never_settle_money(self):
        attempt=self.pending();url=f'/api/payments/mpesa/callback/{attempt.pk}/{attempt.callback_secret}/'
        payload={'Body':{'stkCallback':{'CheckoutRequestID':'checkout','MerchantRequestID':'merchant','ResultCode':0}}}
        public=APIClient()
        self.assertEqual(public.post(url,payload,format='json').status_code,200)
        self.assertEqual(public.post(url,payload,format='json').status_code,200)
        attempt.refresh_from_db();self.assertEqual(attempt.status,'pending');self.assertTrue(attempt.callback_received)
        self.assertEqual(Payment.objects.count(),0)
        payload['Body']['stkCallback']['CheckoutRequestID']='forged'
        self.assertEqual(public.post(url,payload,format='json').status_code,404)
        bad=f'/api/payments/mpesa/callback/{attempt.pk}/{uuid4()}/'
        self.assertEqual(public.post(bad,payload,format='json').status_code,404)

    def test_authenticated_query_can_confirm_only_a_sandbox_result(self):
        attempt=self.pending()
        with patch('core.daraja_views.DarajaSandbox.query',return_value={'ResultCode':'0','CheckoutRequestID':'checkout'}) as remote:
            response=self.client.post(f'/api/payments/mpesa/{attempt.pk}/query/')
            self.assertEqual(response.data['status'],'sandbox_success')
            self.client.post(f'/api/payments/mpesa/{attempt.pk}/query/')
            self.assertEqual(remote.call_count,1)
        self.assertEqual(Payment.objects.count(),0)

    def test_other_accounts_cannot_query_attempts(self):
        attempt=self.pending()
        other=User.objects.create_user(username='other',email='other@mpesa.test',role='manager')
        self.client.force_authenticate(other)
        self.assertEqual(self.client.post(f'/api/payments/mpesa/{attempt.pk}/query/').status_code,404)

    def test_ambiguous_initiation_is_saved_and_not_automatically_repeated(self):
        with patch('core.daraja_views.DarajaSandbox.start',side_effect=DarajaUnavailable('timeout')) as remote:
            self.assertEqual(self.start().data['status'],'unknown')
            self.start();self.assertEqual(remote.call_count,1)
        self.assertEqual(self.start(idempotency_key=str(uuid4())).status_code,409)

    def test_query_outage_or_wrong_checkout_never_confirms(self):
        attempt=self.pending();url=f'/api/payments/mpesa/{attempt.pk}/query/'
        with patch('core.daraja_views.DarajaSandbox.query',side_effect=DarajaUnavailable('offline')):
            self.assertEqual(self.client.post(url).data['status'],'pending')
        with patch('core.daraja_views.DarajaSandbox.query',return_value={'ResultCode':0,'CheckoutRequestID':'wrong'}):
            self.assertEqual(self.client.post(url).data['status'],'unknown')
        self.assertEqual(Payment.objects.count(),0)

    def test_transport_refuses_live_or_disabled_configuration(self):
        with override_settings(DARAJA_ENV='live'),self.assertRaises(DarajaUnavailable):DarajaSandbox()
        with override_settings(DARAJA_SANDBOX_ENABLED=False),self.assertRaises(DarajaUnavailable):DarajaSandbox()

    @override_settings(DARAJA_CALLBACK_BASE_URL='https://callback.example',DARAJA_SHORTCODE='174379',DARAJA_PASSKEY='private-test',DARAJA_CONSUMER_KEY='test',DARAJA_CONSUMER_SECRET='test')
    def test_transport_uses_sandbox_host_and_server_callback(self):
        attempt=SandboxPaymentAttempt.objects.create(requested_by=self.user,tenant=self.tenant,idempotency_key=uuid4(),amount=20000,phone='254712345678')
        responses=[BytesIO(b'{"access_token":"test-only-token"}'),BytesIO(b'{"ResponseCode":"0"}')]
        with patch('core.daraja.urlopen',side_effect=responses) as remote:
            DarajaSandbox().start(attempt)
            self.assertTrue(all(call.args[0].full_url.startswith('https://sandbox.safaricom.co.ke/') for call in remote.call_args_list))
            import json
            body=json.loads(remote.call_args.args[0].data)
            self.assertEqual(body['Amount'],20000)
            self.assertIn(str(attempt.callback_secret),body['CallBackURL'])

    def test_duplicate_provider_identifier_is_kept_as_unknown_without_overwriting(self):
        first=self.pending()
        SandboxPaymentAttempt.objects.filter(pk=first.pk).update(created_at=timezone.now()-timedelta(minutes=3))
        with patch('core.daraja_views.DarajaSandbox.start',return_value={'ResponseCode':'0','CheckoutRequestID':'checkout','MerchantRequestID':'other-merchant'}):
            response=self.start(idempotency_key=str(uuid4()))
        self.assertEqual(response.status_code,202)
        self.assertEqual(response.data['status'],'unknown')
        self.assertEqual(SandboxPaymentAttempt.objects.count(),2)
        first.refresh_from_db();self.assertEqual(first.checkout_request_id,'checkout')
        self.assertEqual(Payment.objects.count(),0)


def ready_monitor_response():
    response=BytesIO(b'{"status":"ready"}')
    response.status=200
    return response


class OperationalMonitoringTests(TestCase):
    def test_internal_proxy_monitor_and_recent_backup_are_healthy(self):
        import io
        import json
        from django.core.management import call_command
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory,SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')):
            snapshot=Path(directory)/'test.snbackup';snapshot.write_bytes(b'encrypted-test-placeholder')
            output=io.StringIO()
            with patch('core.management.commands.check_operations.urlopen',return_value=ready_monitor_response()) as remote:
                call_command('check_operations',backup_dir=directory,host='api.smartnest.test',stdout=output)
            self.assertTrue(json.loads(output.getvalue())['healthy'])
            headers=dict(remote.call_args.args[0].header_items())
            self.assertEqual(headers['X-forwarded-proto'],'https')

    def test_stale_backup_is_reported_but_never_deleted(self):
        import io
        import os
        from django.core.management import call_command, CommandError
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            snapshot=Path(directory)/'old.snbackup';snapshot.write_bytes(b'preserved')
            old=(timezone.now()-timedelta(days=3)).timestamp();os.utime(snapshot,(old,old))
            with patch('core.management.commands.check_operations.urlopen',return_value=ready_monitor_response()):
                with self.assertRaises(CommandError):call_command('check_operations',backup_dir=directory,stdout=io.StringIO())
            self.assertEqual(snapshot.read_bytes(),b'preserved')