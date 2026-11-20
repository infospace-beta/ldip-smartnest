"""Encrypted PostgreSQL/media/key backups and safe restore rehearsals."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZIP_DEFLATED
from cryptography.fernet import Fernet
from django.apps import apps
from django.conf import settings
from django.db.models import FileField
from django.core.management.base import CommandError


def pg_env(database):
    config = settings.DATABASES['default']
    env = os.environ.copy()
    env.update(PGHOST=config['HOST'], PGPORT=str(config['PORT']), PGUSER=config['USER'],
               PGPASSWORD=config['PASSWORD'], PGDATABASE=database,
               PGSSLMODE=config.get('OPTIONS', {}).get('sslmode', 'prefer'))
    return env


def pg_run(program, arguments, database):
    binary = str(Path(os.getenv('PG_BIN', '')) / program) if os.getenv('PG_BIN') else program
    result = subprocess.run([binary, *arguments], env=pg_env(database), capture_output=True, timeout=600)
    if result.returncode:
        # pg tools can echo credentials or data in diagnostics; keep them out of logs.
        raise CommandError(f'{program} failed (exit {result.returncode}); review database connectivity and privileges securely.')


def backup_key():
    try:
        return Fernet(os.environ['SMARTNEST_BACKUP_KEY'].encode())
    except (KeyError, ValueError):
        raise CommandError('Set SMARTNEST_BACKUP_KEY to a private Fernet key stored separately from backups.') from None


def uploaded_names():
    for model in apps.get_app_config('core').get_models():
        for field in model._meta.fields:
            if isinstance(field, FileField):
                yield from model.objects.exclude(**{field.name: ''}).values_list(field.name, flat=True)


def stored_upload_names():
    """Also preserve older/unreferenced files inside known upload directories."""
    root = Path(settings.MEDIA_ROOT).resolve()
    prefixes = set()
    for model in apps.get_app_config('core').get_models():
        for field in model._meta.fields:
            if isinstance(field, FileField) and isinstance(field.upload_to, str):
                prefix = field.upload_to.split('/')[0]
                if prefix and prefix not in ('.', '..') and '%' not in prefix:
                    prefixes.add(prefix)
    names = set()
    for prefix in prefixes:
        directory = safe_file(root, prefix)
        if directory.is_dir():
            for path in directory.rglob('*'):
                if path.is_file():
                    name = path.relative_to(root).as_posix()
                    safe_file(root, name)
                    names.add(name)
    return names


def safe_file(root, name):
    root = Path(root).resolve()
    target = (root / name).resolve()
    if not target.is_relative_to(root) or target == root:
        raise CommandError('Unsafe file path in backup data.')
    return target


def make_backup(output, allow_missing=False):
    cipher = backup_key()
    output = Path(output).resolve()
    if output.exists():
        raise CommandError('Backup destination already exists; refusing to overwrite.')
    config = settings.DATABASES['default']
    if config['ENGINE'] != 'django.db.backends.postgresql':
        raise CommandError('Backups require PostgreSQL.')
    with TemporaryDirectory(prefix='smartnest-backup-') as temp:
        stage = Path(temp)
        os.chmod(stage, 0o700)
        dump = stage / 'database.dump'
        pg_run('pg_dump', ['--format=custom', '--no-owner', '--no-acl', '--file', str(dump)], config['NAME'])
        archive = stage / 'snapshot.zip'
        checksums = {}
        missing = []
        with ZipFile(archive, 'w', ZIP_DEFLATED) as bundle:
            for name in sorted(set(uploaded_names()) | stored_upload_names()):
                path = safe_file(settings.MEDIA_ROOT, name)
                if not path.is_file():
                    if not allow_missing:
                        raise CommandError('A referenced upload is missing; backup aborted. Investigate or explicitly record missing files with --allow-missing.')
                    missing.append(name)
                    continue
                data = path.read_bytes()
                member = f'media/{name}'
                checksums[member] = hashlib.sha256(data).hexdigest()
                bundle.writestr(member, data)
            for member, data in {
                'database.dump': dump.read_bytes(),
                'recovery-secrets.json': json.dumps({
                    'DJANGO_SECRET_KEY': settings.SECRET_KEY,
                    'NOTICE_ENCRYPTION_KEYS': os.getenv('NOTICE_ENCRYPTION_KEYS', ''),
                }).encode(),
            }.items():
                checksums[member] = hashlib.sha256(data).hexdigest()
                bundle.writestr(member, data)
            bundle.writestr('manifest.json', json.dumps({'version': 1, 'sha256': checksums, 'missing_media': missing}))
        output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation avoids overwriting another scheduled backup.
        with output.open('xb') as target:
            os.chmod(output, 0o600)
            target.write(cipher.encrypt(archive.read_bytes()))
    return {'included': len(checksums) - 2, 'missing': len(missing)}


def restore_backup(backup, database, media, secrets):
    # This command deliberately cannot restore over the running database.
    if not database.startswith('smartnest_restore_') or database == settings.DATABASES['default']['NAME']:
        raise CommandError('Use a separate empty database named smartnest_restore_*. Live database restore is refused.')
    import psycopg2
    config = settings.DATABASES['default']
    with psycopg2.connect(dbname=database, host=config['HOST'], port=config['PORT'], user=config['USER'],
                          password=config['PASSWORD'], **config.get('OPTIONS', {})) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema')")
            if cursor.fetchone()[0]:
                raise CommandError('Restore target is not empty.')
    media, secrets = Path(media).resolve(), Path(secrets).resolve()
    live_media = Path(settings.MEDIA_ROOT).resolve()
    if media == live_media or media.is_relative_to(live_media) or live_media.is_relative_to(media):
        raise CommandError('Restore media must be separate from live media.')
    if (media.exists() and any(media.iterdir())) or secrets.exists():
        raise CommandError('Restore destinations must be empty/new.')
    with TemporaryDirectory(prefix='smartnest-restore-') as temp:
        stage = Path(temp)
        os.chmod(stage, 0o700)
        archive = stage / 'snapshot.zip'
        archive.write_bytes(backup_key().decrypt(Path(backup).read_bytes()))
        with ZipFile(archive) as bundle:
            manifest = json.loads(bundle.read('manifest.json'))
            if manifest.get('version') != 1:
                raise CommandError('Unsupported backup version.')
            # Validate everything before writing target data or running pg_restore.
            for member, digest in manifest['sha256'].items():
                if member not in ('database.dump', 'recovery-secrets.json') and not member.startswith('media/'):
                    raise CommandError('Unexpected backup member.')
                if member.startswith('media/'):
                    safe_file(media, member[6:])
                if hashlib.sha256(bundle.read(member)).hexdigest() != digest:
                    raise CommandError('Backup checksum mismatch.')
            dump = stage / 'database.dump'
            dump.write_bytes(bundle.read('database.dump'))
            pg_run('pg_restore', ['--exit-on-error', '--single-transaction', '--no-owner', '--no-acl', '--dbname', database, str(dump)], database)
            media.mkdir(parents=True, exist_ok=True)
            for member in manifest['sha256']:
                if member.startswith('media/'):
                    path = safe_file(media, member[6:])
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(bundle.read(member)); os.chmod(path, 0o600)
            secrets.parent.mkdir(parents=True, exist_ok=True)
            with secrets.open('xb') as target:
                os.chmod(secrets, 0o600)
                target.write(bundle.read('recovery-secrets.json'))
            return len(manifest.get('missing_media', []))
