import json
import shutil
import tempfile
from django.core.files.storage import default_storage
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = 'Read-only operational monitoring: API/worker readiness, persistent media and recent encrypted backup.'

    def add_arguments(self,parser):
        parser.add_argument('--api-url',default='http://127.0.0.1:8000')
        parser.add_argument('--host',default='127.0.0.1')
        parser.add_argument('--backup-dir',required=True)
        parser.add_argument('--max-backup-hours',type=float,default=26)
        parser.add_argument('--min-free-gib',type=float,default=1)
        parser.add_argument('--require-offsite',action='store_true')

    def handle(self,*args,**options):
        remote = getattr(settings, 'SMARTNEST_MEDIA_BACKEND', 'filesystem') == 's3'
        media_available = Path(settings.MEDIA_ROOT).is_dir()
        if remote:
            try:
                default_storage.listdir('')
                media_available = True
            except Exception:
                media_available = False
        status={'api_worker_ready':False,'media_directory_present':media_available,'media_backend':'s3' if remote else 'filesystem','recent_backup':False}
        headers={'Host':options['host']}
        target=urlsplit(options['api_url'])
        if target.scheme=='http' and target.hostname in ('127.0.0.1','::1','localhost') and getattr(settings,'SECURE_PROXY_SSL_HEADER',None)==('HTTP_X_FORWARDED_PROTO','https'):
            headers['X-Forwarded-Proto']='https'
        request=Request(options['api_url'].rstrip('/')+'/api/health/ready/',headers=headers)
        try:
            with urlopen(request,timeout=10) as response:
                payload=json.load(response)
                status['api_worker_ready']=response.status==200 and isinstance(payload,dict) and payload.get('status')=='ready'
        except (HTTPError,URLError,TimeoutError,ValueError,OSError):
            pass
        backups=list(Path(options['backup_dir']).glob('*.snbackup'))
        if backups:
            newest=max(backups,key=lambda p:p.stat().st_mtime)
            age=(timezone.now().timestamp()-newest.stat().st_mtime)/3600
            status['backup_age_hours']=round(age,2)
            status['recent_backup']=newest.stat().st_size>0 and 0<=age<=options['max_backup_hours']
        disk_path = tempfile.gettempdir() if remote else settings.MEDIA_ROOT
        free_gib=shutil.disk_usage(disk_path).free/(1024**3) if Path(disk_path).is_dir() else 0
        status['disk_free_gib']=round(free_gib,2)
        status['enough_disk_space']=free_gib>=max(0,options['min_free_gib'])
        checks=['api_worker_ready','media_directory_present','recent_backup','enough_disk_space']
        if options['require_offsite']:
            marker=Path(options['backup_dir'])/'.last-offsite-success'
            age=(timezone.now().timestamp()-marker.stat().st_mtime)/3600 if marker.is_file() else None
            status['recent_offsite_transfer']=age is not None and 0<=age<=options['max_backup_hours']
            checks.append('recent_offsite_transfer')
        status['healthy']=all(status[key] for key in checks)
        self.stdout.write(json.dumps(status))
        if not status['healthy']:
            raise CommandError('Operational monitoring found an unavailable component; no data was changed.')
