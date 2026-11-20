import json
from django.core.management.base import BaseCommand
from core.sms import deliver_notifications


class Command(BaseCommand):
    help = 'Submit opted-in notification SMS through Twilio; use --dry-run to inspect counts without sending.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--limit', type=int, default=50)

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(deliver_notifications(max(1, min(options['limit'], 100)), options['dry_run'])))
