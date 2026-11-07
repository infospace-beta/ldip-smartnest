from django.core.management.base import BaseCommand
from core.recovery import restore_backup


class Command(BaseCommand):
    help = 'Restore a trusted encrypted backup to a separate empty rehearsal database/media location.'

    def add_arguments(self, parser):
        parser.add_argument('--backup', required=True)
        parser.add_argument('--database', required=True)
        parser.add_argument('--media', required=True)
        parser.add_argument('--secrets', required=True)

    def handle(self, *args, **options):
        missing = restore_backup(options['backup'], options['database'], options['media'], options['secrets'])
        if missing:
            self.stderr.write(self.style.WARNING(f'{missing} file references were already missing at capture. This restore cannot recover their bytes.'))
        self.stdout.write(self.style.SUCCESS('Restore completed in the separate target. Validate counts, files and decryption before promotion.'))
