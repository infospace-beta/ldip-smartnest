"""Offline production environment validation. Reports missing names, never secret values."""
import argparse
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from dotenv import dotenv_values
from cryptography.fernet import Fernet

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--backend-env',type=Path,required=True)
parser.add_argument('--frontend-env',type=Path,required=True)
parser.add_argument('--backup-env',type=Path,required=True)
args=parser.parse_args()
for file in (args.backend_env,args.frontend_env,args.backup_env):
    if not file.is_file():parser.error('An environment file is missing; no configuration was changed.')
backend=dotenv_values(args.backend_env);frontend=dotenv_values(args.frontend_env);backup=dotenv_values(args.backup_env)
errors=[]
def actual(value):
    return isinstance(value,str) and bool(value.strip()) and not any(marker in value.lower() for marker in ('replace-with','your-domain','your-project','your-rclone','private-database-host','your_account','your_private'))
def require(values,names):
    for name in names:
        if not actual(values.get(name)):errors.append(name)
def https_origin(value):
    try:
        parsed=urlsplit(value or '')
        return parsed.scheme=='https' and parsed.hostname and not parsed.hostname.endswith(('.example','.invalid')) and parsed.hostname!='localhost' and not parsed.username and not parsed.password
    except ValueError:return False
require(backend,['DJANGO_SECRET_KEY','NOTICE_ENCRYPTION_KEYS','DJANGO_ALLOWED_HOSTS','DB_NAME','DB_USER','DB_PASSWORD','DB_HOST','DB_PORT','DB_SSLMODE','DJANGO_STATIC_ROOT','SUPABASE_URL','SUPABASE_PUBLISHABLE_KEY','FRONTEND_URL','DJANGO_CORS_ORIGINS','DJANGO_CSRF_ORIGINS'])
if backend.get('DJANGO_ENV')!='production':errors.append('DJANGO_ENV=production')
if backend.get('DEBUG','').lower()!='false':errors.append('DEBUG=false')
if len(backend.get('DJANGO_SECRET_KEY') or '')<50:errors.append('DJANGO_SECRET_KEY length')
if backend.get('DB_USER','').lower() in ('postgres','root') or backend.get('DB_SSLMODE') not in ('require','verify-ca','verify-full'):errors.append('restricted DB user and database TLS')
if backend.get('SUPABASE_AUTH_ENABLED','').lower()!='true':errors.append('SUPABASE_AUTH_ENABLED=true')
for name in ('FRONTEND_URL','DJANGO_CORS_ORIGINS','DJANGO_CSRF_ORIGINS'):
    for origin in (backend.get(name) or '').split(','):
        if not https_origin(origin.strip()) or '*' in origin:errors.append(name+' HTTPS origins')
remote=backend.get('SMARTNEST_MEDIA_BACKEND','filesystem')=='s3'
if remote:
    require(backend,['SMARTNEST_S3_ENDPOINT','SMARTNEST_S3_ACCESS_KEY','SMARTNEST_S3_SECRET_KEY','SMARTNEST_MEDIA_BUCKET'])
    if not https_origin(backend.get('SMARTNEST_S3_ENDPOINT')):errors.append('private S3 HTTPS endpoint')
else:
    require(backend,['DJANGO_MEDIA_ROOT'])
for name in (() if remote else ('DJANGO_MEDIA_ROOT',)):
    path=PurePosixPath(backend.get(name) or '')
    if not path.is_absolute() or any(path.is_relative_to(prefix) for prefix in ('/tmp','/run','/var/tmp','/opt/smartnest')):errors.append(name+' persistent path outside application')
require(frontend,['NEXT_PUBLIC_SITE_URL','NEXT_PUBLIC_API_URL','NEXT_PUBLIC_SUPABASE_URL','NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY'])
for name in ('NEXT_PUBLIC_SITE_URL','NEXT_PUBLIC_API_URL','NEXT_PUBLIC_SUPABASE_URL'):
    if not https_origin(frontend.get(name)):errors.append(name+' HTTPS URL')
if frontend.get('NEXT_PUBLIC_SITE_URL','').rstrip('/')!=backend.get('FRONTEND_URL','').rstrip('/'):errors.append('matching frontend origins')
require(backup,['SMARTNEST_BACKUP_KEY'])
if remote:
    require(backup,['SMARTNEST_BACKUP_BUCKET'])
    if backup.get('SMARTNEST_BACKUP_BUCKET')==backend.get('SMARTNEST_MEDIA_BUCKET'):errors.append('separate private backup bucket')
else:
    require(backup,['SMARTNEST_OFFSITE_DEST','RCLONE_CONFIG'])
try:Fernet((backup.get('SMARTNEST_BACKUP_KEY') or '').encode())
except (ValueError,TypeError):errors.append('valid separate backup encryption key')
if backend.get('SMARTNEST_SMS_ENABLED','').lower()=='true':require(backend,['TWILIO_ACCOUNT_SID','TWILIO_AUTH_TOKEN','TWILIO_MESSAGING_SERVICE_SID'])
if backend.get('DARAJA_SANDBOX_ENABLED','').lower()=='true':
    require(backend,['DARAJA_CONSUMER_KEY','DARAJA_CONSUMER_SECRET','DARAJA_SHORTCODE','DARAJA_PASSKEY','DARAJA_CALLBACK_BASE_URL'])
    if not https_origin(backend.get('DARAJA_CALLBACK_BASE_URL')):errors.append('DARAJA_CALLBACK_BASE_URL HTTPS URL')
require(backend,['EMAIL_HOST','EMAIL_HOST_USER','EMAIL_HOST_PASSWORD','DEFAULT_FROM_EMAIL','SMARTNEST_ALERT_EMAIL'])
if backend.get('DJANGO_EMAIL_BACKEND')!='django.core.mail.backends.smtp.EmailBackend':errors.append('production SMTP backend')
if backend.get('EMAIL_USE_TLS','').lower()!='true':errors.append('EMAIL_USE_TLS=true')
for name in ('DEFAULT_FROM_EMAIL','SMARTNEST_ALERT_EMAIL'):
    if '.local' in (backend.get(name) or '') or '.example' in (backend.get(name) or ''):errors.append(name+' real domain')
if backend.get('DARAJA_ENV','sandbox')!='sandbox':errors.append('DARAJA_ENV=sandbox (live settlement is not implemented)')
if errors:
    print('NOT READY. Configure these items; values are hidden:')
    print('\n'.join('- '+name for name in sorted(set(errors))))
    raise SystemExit(1)
print('Offline environment checks passed. Still verify DNS, certificates, provider activation, static routing, restore recovery, offsite credentials and service behavior on staging.')
