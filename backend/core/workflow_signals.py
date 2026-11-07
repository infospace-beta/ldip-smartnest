from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import TenancyEvent, User
from .workflow_service import create_inspection, policy_for


@receiver(post_save, sender=TenancyEvent)
def inspect_tenancy_event(sender, instance, created, **kwargs):
    if created and not kwargs.get('raw'):
        create_inspection(instance.tenant, 'move_in' if instance.action=='check_in' else 'move_out',source=instance)


@receiver(post_save, sender=User)
def manager_policy(sender, instance, created, **kwargs):
    if instance.role=='manager' and not kwargs.get('raw'):
        policy_for(instance)
