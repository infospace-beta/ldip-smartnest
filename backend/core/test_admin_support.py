from django.test import TestCase,override_settings
from rest_framework.test import APIClient
from .models import User,Property,Unit,Tenant


@override_settings(SUPABASE_AUTH_ENABLED=False)
class AdministratorSupportTests(TestCase):
    def setUp(self):
        self.client=APIClient()
        self.admin=User.objects.create_user(username='support-admin',email='support-admin@example.test',role='admin')
        self.other_admin=User.objects.create_user(username='other-admin',email='other-admin@example.test',role='admin')
        self.manager=User.objects.create_user(username='manager',email='manager@example.test',role='manager')
        self.staff=User.objects.create_user(username='staff',email='staff@example.test',role='staff')
        self.maintenance=User.objects.create_user(username='maintenance',email='maintenance@example.test',role='maintenance')
        self.tenant=User.objects.create_user(username='tenant',email='tenant@example.test',role='tenant',portal_access_granted=True)
        prop=Property.objects.create(name='Support test',location='Nairobi',owner=self.manager)
        unit=Unit.objects.create(property=prop,unit_number='A1',unit_type='Studio',rent='10000')
        Tenant.objects.create(user=self.tenant,name='Tenant',phone='0712345678',property=prop,unit=unit,lease_end='2027-12-31',rent='10000')

    def start(self,user,recipient=None,body='The dashboard failed to load.'):
        self.client.force_authenticate(user)
        return self.client.post('/api/communication/conversations/',{'recipient':(recipient or self.admin).pk,'subject':'[Support] Dashboard failure','body':body},format='json')

    def test_every_non_admin_role_can_contact_admin_and_receive_a_reply(self):
        for user in [self.manager,self.staff,self.maintenance,self.tenant]:
            with self.subTest(role=user.role):
                self.client.force_authenticate(user)
                contacts=self.client.get('/api/communication/contacts/')
                self.assertIn(self.admin.pk,[entry['id'] for entry in contacts.data])
                started=self.start(user)
                self.assertEqual(started.status_code,201,started.data)
                self.assertEqual({entry['id'] for entry in started.data['participants']},{user.pk,self.admin.pk})
                self.client.force_authenticate(self.admin)
                inbox=self.client.get('/api/communication/conversations/')
                self.assertIn(started.data['id'],[entry['id'] for entry in inbox.data])
                path=f"/api/communication/conversations/{started.data['id']}/messages/"
                self.assertEqual(self.client.post(path,{'body':'We are investigating.'},format='json').status_code,201)
                self.client.force_authenticate(user)
                messages=self.client.get(path)
                self.assertEqual([entry['body'] for entry in messages.data],['The dashboard failed to load.','We are investigating.'])

    def test_support_conversations_remain_private_even_from_other_admins(self):
        started=self.start(self.staff)
        for outsider in [self.other_admin,self.manager,self.maintenance]:
            self.client.force_authenticate(outsider)
            self.assertNotIn(started.data['id'],[entry['id'] for entry in self.client.get('/api/communication/conversations/').data])
            self.assertEqual(self.client.get(f"/api/communication/conversations/{started.data['id']}/messages/").status_code,404)

    def test_inactive_administrators_cannot_receive_support_requests(self):
        self.admin.is_active_user=False;self.admin.save(update_fields=['is_active_user'])
        self.client.force_authenticate(self.staff)
        self.assertNotIn(self.admin.pk,[entry['id'] for entry in self.client.get('/api/communication/contacts/').data])
        self.assertEqual(self.start(self.staff).status_code,403)

    def test_support_permission_does_not_expand_other_property_contacts(self):
        unrelated=User.objects.create_user(username='unrelated',email='unrelated@example.test',role='manager')
        self.assertEqual(self.start(self.tenant,unrelated).status_code,403)
        self.assertEqual(self.start(self.staff,self.tenant).status_code,403)

    def test_empty_messages_are_rejected(self):
        self.assertEqual(self.start(self.staff,body='   ').status_code,400)
