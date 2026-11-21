import json
import logging
import os
import time
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.utils import timezone
from core.workflow_service import process_automations
from core.backup_lock import application_lock

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process automations; deploy one supervised worker per environment.'

    def add_arguments(self, parser):
        parser.add_argument('--loop', action='store_true')
        parser.add_argument('--interval', type=int, default=60)

    def handle(self, *args, **options):
        failures = 0
        while True:
            close_old_connections()
            try:
                with application_lock():
                    result = process_automations()
                    if settings.SMARTNEST_SMS_ENABLED:
                        from core.sms import deliver_notifications
                        result['sms'] = deliver_notifications()
                if result.get('failures'):
                    raise CommandError('One or more automation policies failed; inspect policy IDs in the log.')
                heartbeat = settings.AUTOMATION_HEARTBEAT_PATH
                heartbeat.parent.mkdir(parents=True, exist_ok=True)
                temporary = heartbeat.with_name(f'{heartbeat.name}.{os.getpid()}.tmp')
                temporary.write_text(timezone.now().isoformat(), encoding='utf-8')
                os.replace(temporary, heartbeat)
                self.stdout.write(json.dumps(result))
                failures = 0
            except Exception as error:
                # Do not write exception values that could contain connection secrets.
                logger.error('Automation pass failed error_type=%s', type(error).__name__)
                if not options['loop']:
                    raise CommandError('Automation pass failed. No successful heartbeat recorded.') from None
                failures += 1
            finally:
                close_old_connections()
            if not options['loop']:
                return
            time.sleep(min(300, max(10, options['interval']) * (2 ** min(failures, 3))))
