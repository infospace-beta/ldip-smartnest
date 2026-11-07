import base64
import hashlib
import hmac
import json
from datetime import timedelta
from cryptography.fernet import Fernet
from django.conf import settings
from django.db import migrations
from django.utils import timezone


def prepare(apps,schema_editor):
    Notice=apps.get_model('core','Notice')
    key=base64.urlsafe_b64encode(hmac.new(settings.SECRET_KEY.encode(),b'smartnest-notices-v1',hashlib.sha256).digest())
    cipher=Fernet(key)
    for n in Notice.objects.all().iterator():
        if not n.encrypted_content:
            n.encrypted_content=cipher.encrypt(json.dumps({'title':n.title,'text':n.text}).encode()).decode()
            n.title='';n.text='';n.save(update_fields=['title','text','encrypted_content'])
    # Recipientless historical notices are kept private until recipients are known.
    Policy=apps.get_model('core','WorkflowPolicy')
    for u in apps.get_model('core','User').objects.filter(role='manager'):
        Policy.objects.get_or_create(manager=u,defaults={'enabled':False})
    Inspection=apps.get_model('core','UnitInspection')
    Inspection.objects.filter(scheduled_at__isnull=True,tenant__isnull=True).update(status='closed')
    Job=apps.get_model('core','MaintenanceJob');Offer=apps.get_model('core','MaintenanceOffer');Conversation=apps.get_model('core','Conversation')
    for j in Job.objects.filter(status='assigned',assigned_to__isnull=False,property__owner__isnull=False):
        Offer.objects.get_or_create(job=j,provider=j.assigned_to,defaults={'expires_at':timezone.now()+timedelta(hours=24)})
        if j.reported_by_user_id and not j.conversation_id:
            c=Conversation.objects.create(subject=f'{j.job_id}: {j.issue}'[:200],created_by_id=j.property.owner_id)
            c.participants.set([j.reported_by_user_id,j.assigned_to_id]);j.conversation=c;j.save(update_fields=['conversation'])


class Migration(migrations.Migration):
    dependencies=[('core','0020_invitation_scope_and_moveout')]
    operations=[migrations.RunPython(prepare,migrations.RunPython.noop)]
