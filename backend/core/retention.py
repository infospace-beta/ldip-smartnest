from django.db.models.deletion import ProtectedError
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from .models import Tenant, TenancyEvent


@receiver(pre_delete, sender=Tenant, dispatch_uid='retain_tenancy_records')
@receiver(pre_delete, sender=TenancyEvent, dispatch_uid='retain_tenancy_events')
def retain_tenancy_history(sender, instance, **kwargs):
    raise ProtectedError('Tenancy records and handover history are retained. Record a move-out or disable access instead of deleting history.', [instance])
