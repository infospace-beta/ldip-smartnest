from django.core.management.base import BaseCommand, CommandError
from core.recovery import make_backup


class Command(BaseCommand):
    help = 'Encrypt a PostgreSQL, referenced-media and notice-key snapshot. Quiesce writes during capture.'

    def add_arguments(self, parser):
        parser.add_argument('--output', required=True)
        parser.add_argument('--allow-missing', action='store_true', help='Record preexisting missing file references; do not claim a complete media snapshot.')
        parser.add_argument('--quiesced', action='store_true', help='Confirm application writes/uploads are paused for the snapshot.')

    def handle(self, *args, **options):
        if not options['quiesced']:
            raise CommandError('Pause application writes/uploads, then pass --quiesced. Database and media need a consistent snapshot.')
        result = make_backup(options['output'], allow_missing=options['allow_missing'])
        self.stdout.write(self.style.SUCCESS(f"Encrypted backup created; {result['included']} referenced uploads included."))
        if result['missing']:
            self.stderr.write(self.style.WARNING(f"Incomplete source media: {result['missing']} missing references recorded in encrypted manifest. No database references changed."))
