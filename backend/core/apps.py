from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        from . import workflow_signals  # noqa: F401
        from django.db.models.signals import m2m_changed
        from .models import Notice
        from .sms import queue_notice_sms
        m2m_changed.connect(queue_notice_sms, sender=Notice.recipients.through,
                            dispatch_uid='smartnest_notice_sms')
