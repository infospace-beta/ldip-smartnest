import hashlib
from pathlib import Path
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from core.recovery import uploaded_names, safe_file


def digest(file):
    result = hashlib.sha256()
    for chunk in iter(lambda: file.read(1024 * 1024), b''):
        result.update(chunk)
    return result.hexdigest()


class Command(BaseCommand):
    help = 'Copy and verify existing private media without renaming records, overwriting objects, or removing local files.'

    def add_arguments(self, parser):
        parser.add_argument('--source-root', required=True)
        parser.add_argument('--quiesced', action='store_true')
        parser.add_argument('--verify-only', action='store_true')

    def handle(self, *args, **options):
        from django.conf import settings
        if settings.SMARTNEST_MEDIA_BACKEND != 's3':
            raise CommandError('Select the private S3 backend before copying files.')
        if not options['verify_only'] and not options['quiesced']:
            raise CommandError('Pause writers/uploads and pass --quiesced before copying media.')
        source = Path(options['source_root']).resolve()
        names = set(uploaded_names())
        # Include older files as well as current references; never silently lose history.
        if not source.is_dir():
            raise CommandError('The source media directory does not exist.')
        prefixes = {'profile-photos', 'maintenance', 'maintenance-completion', 'tenancy-events', 'inspection-photos'}
        for prefix in prefixes:
            directory = safe_file(source, prefix)
            if directory.is_dir():
                names.update(p.relative_to(source).as_posix() for p in directory.rglob('*') if p.is_file())
        copied, verified = 0, 0
        for name in sorted(names):
            local = safe_file(source, name)
            if not local.is_file():
                raise CommandError('A referenced local upload is missing. No database links were changed.')
            with local.open('rb') as file:
                expected = digest(file)
            if not default_storage.exists(name):
                if options['verify_only']:
                    raise CommandError('An upload has not reached the destination.')
                with local.open('rb') as file:
                    stored = default_storage.save(name, File(file))
                if stored != name:
                    raise CommandError('Storage returned a different key. No database links were changed; inspect the destination before continuing.')
                copied += 1
            with default_storage.open(name, 'rb') as file:
                if digest(file) != expected:
                    raise CommandError('Destination content differs. Existing objects and local files were preserved.')
            verified += 1
        self.stdout.write(f'Copied {copied} uploads; verified {verified} checksums. Local files and database links were preserved.')
