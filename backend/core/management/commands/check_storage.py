import json
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from core.recovery import uploaded_names, stored_upload_names, safe_file


class Command(BaseCommand):
    help = 'Read-only persistent storage audit. Never prunes records or files.'

    def add_arguments(self, parser):
        parser.add_argument('--deployment',action='store_true')

    def handle(self,*args,**options):
        root=Path(settings.MEDIA_ROOT).resolve()
        names=set(uploaded_names())
        missing=sum(not safe_file(root,name).is_file() for name in names)
        outside=not root.is_relative_to(settings.BASE_DIR.parent.resolve())
        result={'database_engine':settings.DATABASES['default']['ENGINE'],'media_exists':root.is_dir(),
            'media_outside_project':outside,'referenced_uploads':len(names),
            'stored_uploads':len(stored_upload_names()),'missing_referenced_uploads':missing,
            'automatic_record_expiry':False}
        self.stdout.write(json.dumps(result))
        if missing or not root.is_dir() or (options['deployment'] and not outside):
            raise CommandError('Persistent storage audit failed; no records or files were changed.')
