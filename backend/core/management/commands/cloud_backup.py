import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.files.storage import default_storage
from core.backup_lock import application_lock, BackupInProgress
from core.recovery import make_backup


class Command(BaseCommand):
    help = 'Create a coordinated encrypted snapshot and upload it to a separate private S3-compatible backup bucket. Never prunes history.'

    def add_arguments(self, parser):
        parser.add_argument('--verify-key', help='Read/decrypt an existing backup key and verify its member checksums without restoring live data.')

    def handle(self, *args, **options):
        from boto3 import client
        from botocore.config import Config
        from core.recovery import backup_key
        required = ['SMARTNEST_S3_ENDPOINT', 'SMARTNEST_S3_ACCESS_KEY', 'SMARTNEST_S3_SECRET_KEY', 'SMARTNEST_BACKUP_BUCKET', 'SMARTNEST_BACKUP_KEY']
        if any(not os.getenv(name) for name in required):
            raise CommandError('Configure the private storage and separate backup credentials before enabling cloud backups. Values are hidden.')
        bucket = os.environ['SMARTNEST_BACKUP_BUCKET']
        if bucket == os.getenv('SMARTNEST_MEDIA_BUCKET'):
            raise CommandError('Backups require a separate private bucket.')
        storage = client('s3', endpoint_url=os.environ['SMARTNEST_S3_ENDPOINT'], region_name=os.getenv('SMARTNEST_S3_REGION', 'ap-south-1'),
                         aws_access_key_id=os.environ['SMARTNEST_S3_ACCESS_KEY'], aws_secret_access_key=os.environ['SMARTNEST_S3_SECRET_KEY'],
                         config=Config(signature_version='s3v4', s3={'addressing_style': 'path'}, request_checksum_calculation='when_required', response_checksum_validation='when_required', connect_timeout=10, read_timeout=30, retries={'max_attempts': 2}))
        maximum = int(os.getenv('SMARTNEST_BACKUP_MAX_BYTES', str(45 * 1024 * 1024)))
        try:
            if options['verify_key']:
                from io import BytesIO
                from zipfile import ZipFile
                response = storage.get_object(Bucket=bucket, Key=options['verify_key'])
                if response['ContentLength'] > maximum:
                    raise CommandError('Backup exceeds the configured verification limit.')
                encrypted = response['Body'].read(maximum + 1)
                with ZipFile(BytesIO(backup_key().decrypt(encrypted))) as archive:
                    manifest = json.loads(archive.read('manifest.json'))
                    for name, expected in manifest['sha256'].items():
                        if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                            raise CommandError('Backup member checksum mismatch.')
                self.stdout.write('Offsite encrypted backup decrypts and all member checksums match. No live data was restored.')
                return
            with application_lock(exclusive=True, wait_seconds=60), TemporaryDirectory(prefix='smartnest-cloud-backup-') as directory:
                snapshot = Path(directory) / 'snapshot.snbackup'
                result = make_backup(snapshot)
                if snapshot.stat().st_size > maximum:
                    raise CommandError('Snapshot exceeds the configured free-tier upload limit. No offsite file was uploaded.')
                stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
                key = f'encrypted/smartnest_{stamp}.snbackup'
                content = snapshot.read_bytes()
                digest = hashlib.sha256(content).hexdigest()
                storage.put_object(Bucket=bucket, Key=key, Body=content, ContentType='application/octet-stream', CacheControl='private, no-store', Metadata={'sha256': digest})
                remote = storage.get_object(Bucket=bucket, Key=key)
                if hashlib.sha256(remote['Body'].read(maximum + 1)).hexdigest() != digest:
                    raise CommandError('Uploaded backup checksum did not match. Existing snapshots were preserved.')
                self.stdout.write(json.dumps({'key': key, 'stored_uploads': result['included'], 'missing_files': result['missing'], 'offsite_checksum_verified': True, 'automatic_pruning': False}))
        except BackupInProgress as error:
            raise CommandError(str(error)) from None
        except CommandError:
            raise
        except Exception:
            raise CommandError('Cloud backup failed. Check connectivity, bucket privacy and access securely; credential values are hidden.') from None
