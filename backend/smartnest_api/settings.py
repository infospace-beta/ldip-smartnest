"""
Django settings for smartnest_api project.
"""

from pathlib import Path
from datetime import timedelta
import os
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
# An explicitly selected private environment is loaded before local defaults.
private_environment = os.getenv('SMARTNEST_ENV_FILE')
if private_environment:
    if not Path(private_environment).is_file():
        raise ImproperlyConfigured('The selected private environment file does not exist.')
    load_dotenv(private_environment, override=False)
# Process variables take precedence; .env supplies the local database settings.
load_dotenv(BASE_DIR / '.env', override=False)
load_dotenv(BASE_DIR / '.env.local', override=False)

# One stable, private value must be shared by every process in a deployment.
# No fallback: replacing the committed key invalidates its existing signatures.
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', '')
if len(SECRET_KEY.strip()) < 50 or SECRET_KEY.startswith('django-insecure-'):
    raise ImproperlyConfigured(
        'Set DJANGO_SECRET_KEY to a private, randomly generated value of at least 50 characters.'
    )

def env_bool(name, default=False):
    value = os.getenv(name, str(default)).strip().lower()
    if value not in ('true', 'false', '1', '0'):
        raise ImproperlyConfigured(f'{name} must be true or false.')
    return value in ('true', '1')


def env_list(name, default=''):
    return [value.strip() for value in os.getenv(name, default).split(',') if value.strip()]


ENVIRONMENT = os.getenv('DJANGO_ENV', 'development')
if ENVIRONMENT not in ('development', 'test', 'production'):
    raise ImproperlyConfigured('DJANGO_ENV must be development, test or production.')
PRODUCTION = ENVIRONMENT == 'production'
DEBUG = env_bool('DEBUG', not PRODUCTION)
ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', '' if PRODUCTION else 'localhost,127.0.0.1,[::1],testserver')
if PRODUCTION and (DEBUG or not ALLOWED_HOSTS or '*' in ALLOWED_HOSTS):
    raise ImproperlyConfigured('Production requires DEBUG=false and explicit DJANGO_ALLOWED_HOSTS.')
if PRODUCTION and not os.getenv('NOTICE_ENCRYPTION_KEYS'):
    raise ImproperlyConfigured('Production requires separately backed-up NOTICE_ENCRYPTION_KEYS.')
if os.getenv('NOTICE_ENCRYPTION_KEYS'):
    from cryptography.fernet import Fernet
    try:
        for key in env_list('NOTICE_ENCRYPTION_KEYS'):
            Fernet(key.encode())
    except ValueError:
        raise ImproperlyConfigured('NOTICE_ENCRYPTION_KEYS must contain valid Fernet keys.') from None

SECURE_SSL_REDIRECT = PRODUCTION
SESSION_COOKIE_SECURE = PRODUCTION
CSRF_COOKIE_SECURE = PRODUCTION
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_HSTS_SECONDS = 31536000 if PRODUCTION else 0
# Opt in only after verifying every subdomain supports HTTPS.
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('DJANGO_HSTS_SUBDOMAINS')
SECURE_HSTS_PRELOAD = env_bool('DJANGO_HSTS_PRELOAD')
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
if env_bool('DJANGO_TRUST_PROXY_HTTPS'):
    # The proxy must strip client-supplied forwarding headers before setting this.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third party
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',

    # Local
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.audit_middleware.AuditMiddleware',
    'core.backup_lock.BackupCoordinationMiddleware',
]

if PRODUCTION:
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

ROOT_URLCONF = 'smartnest_api.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'smartnest_api.wsgi.application'

# Runtime database credentials are external to source control.
DATABASES = {'default': {
    'ENGINE': 'django.db.backends.postgresql',
    'NAME': os.getenv('DB_NAME', 'smartnest_db'),
    'USER': os.getenv('DB_USER', ''),
    'PASSWORD': os.getenv('DB_PASSWORD', ''),
    'HOST': os.getenv('DB_HOST', '127.0.0.1'),
    'PORT': os.getenv('DB_PORT', '5432'),
    'CONN_MAX_AGE': 60,
    'OPTIONS': {'connect_timeout': 5, 'sslmode': os.getenv('DB_SSLMODE', 'require' if PRODUCTION else 'prefer')},
}}
# Keep Django tables outside Supabase's exposed public schema when configured.
database_schema = os.getenv('DB_SCHEMA', '')
if database_schema:
    if not database_schema.isascii() or not database_schema.replace('_', '').isalnum() or not database_schema[0].isalpha():
        raise ImproperlyConfigured('DB_SCHEMA must start with a letter and contain only ASCII letters, digits or underscores.')
    DATABASES['default']['OPTIONS']['options'] = f'-c search_path={database_schema}'
if PRODUCTION and (not DATABASES['default']['PASSWORD'] or not DATABASES['default']['USER']
                   or DATABASES['default']['USER'].lower() in ('postgres', 'root')
                   or DATABASES['default']['OPTIONS']['sslmode'] not in ('require', 'verify-ca', 'verify-full')):
    raise ImproperlyConfigured('Production requires private credentials for a non-superuser DB account and database TLS.')

# Custom user model
AUTH_USER_MODEL = 'core.User'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'
STATIC_ROOT = Path(os.getenv('DJANGO_STATIC_ROOT', str(BASE_DIR / 'staticfiles')))
# This path must be private, persistent and backed up; never expose it through a web alias.
MEDIA_ROOT = Path(os.getenv('DJANGO_MEDIA_ROOT', str(BASE_DIR)))
MEDIA_URL = '/private-media/'
FILE_UPLOAD_PERMISSIONS = 0o600
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
AUTOMATION_HEARTBEAT_PATH = Path(os.getenv('AUTOMATION_HEARTBEAT_PATH', str(BASE_DIR / '.automation-heartbeat')))
AUTOMATION_HEARTBEAT_MAX_AGE = int(os.getenv('AUTOMATION_HEARTBEAT_MAX_AGE', '180'))
SMARTNEST_MEDIA_BACKEND = os.getenv('SMARTNEST_MEDIA_BACKEND', 'filesystem')
from core.storage_config import configured_storages
STORAGES = configured_storages(SMARTNEST_MEDIA_BACKEND)
if PRODUCTION and SMARTNEST_MEDIA_BACKEND == 'filesystem' and (not os.getenv('DJANGO_MEDIA_ROOT') or not MEDIA_ROOT.is_absolute()):
    raise ImproperlyConfigured('Production requires an absolute private persistent DJANGO_MEDIA_ROOT.')

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django REST Framework
SUPABASE_URL = os.getenv('SUPABASE_URL', '').rstrip('/')
SUPABASE_PUBLISHABLE_KEY = os.getenv('SUPABASE_PUBLISHABLE_KEY', '')
SUPABASE_AUTH_ENABLED = env_bool('SUPABASE_AUTH_ENABLED')
if PRODUCTION and not SUPABASE_AUTH_ENABLED:
    raise ImproperlyConfigured('Production requires Supabase authentication.')
if SUPABASE_AUTH_ENABLED and (
    not SUPABASE_URL.startswith('https://') or not SUPABASE_PUBLISHABLE_KEY
):
    raise ImproperlyConfigured('Supabase Auth requires an HTTPS SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY.')

REST_FRAMEWORK = {
    'EXCEPTION_HANDLER': 'core.api_exceptions.exception_handler',
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'core.supabase_auth.SupabaseAuthentication' if SUPABASE_AUTH_ENABLED
        else 'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_RATES': {
        'password_reset': '3/hour',
    },
}

# JWT Settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'CHECK_REVOKE_TOKEN': True,
}

EMAIL_BACKEND = os.getenv(
    'DJANGO_EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend',
)
EMAIL_TIMEOUT = 10
EMAIL_HOST = os.getenv('EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'true').lower() == 'true'
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'SmartNest <no-reply@smartnest.local>')

# Frontend
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000').rstrip('/')

# Explicit origins even in development; no credentialed wildcard access.
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True
default_origins = '' if PRODUCTION else 'http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001'
CORS_ALLOWED_ORIGINS = env_list('DJANGO_CORS_ORIGINS', default_origins)
CSRF_TRUSTED_ORIGINS = env_list('DJANGO_CSRF_ORIGINS', default_origins)
if PRODUCTION and (not FRONTEND_URL.startswith('https://') or not CORS_ALLOWED_ORIGINS
                   or not CSRF_TRUSTED_ORIGINS
                   or any(not origin.startswith('https://') or '*' in origin for origin in CORS_ALLOWED_ORIGINS + CSRF_TRUSTED_ORIGINS)):
    raise ImproperlyConfigured('Production requires HTTPS FRONTEND_URL and explicit HTTPS CORS/CSRF origins.')

LOGGING = {
    'version': 1, 'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {'core': {'handlers': ['console'], 'level': 'INFO', 'propagate': False}},
}


# Notification SMS is opt-in and stays disabled until a provider is configured.
# Sign-in OTP provider credentials belong in Supabase Auth, never in browser env.
SMARTNEST_SMS_ENABLED = env_bool('SMARTNEST_SMS_ENABLED')
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN', '')
TWILIO_MESSAGING_SERVICE_SID = os.getenv('TWILIO_MESSAGING_SERVICE_SID', '')
if SMARTNEST_SMS_ENABLED and not all((TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_MESSAGING_SERVICE_SID)):
    raise ImproperlyConfigured('SMS notifications require complete Twilio credentials.')


# Daraja is sandbox-only. Enabling this does not enable real rent settlement.
DARAJA_SANDBOX_ENABLED = env_bool('DARAJA_SANDBOX_ENABLED')
DARAJA_ENV = os.getenv('DARAJA_ENV', 'sandbox')
DARAJA_CONSUMER_KEY = os.getenv('DARAJA_CONSUMER_KEY', '')
DARAJA_CONSUMER_SECRET = os.getenv('DARAJA_CONSUMER_SECRET', '')
DARAJA_SHORTCODE = os.getenv('DARAJA_SHORTCODE', '')
DARAJA_PASSKEY = os.getenv('DARAJA_PASSKEY', '')
DARAJA_CALLBACK_BASE_URL = os.getenv('DARAJA_CALLBACK_BASE_URL', '').rstrip('/')
if DARAJA_ENV != 'sandbox':
    raise ImproperlyConfigured('This integration supports Daraja sandbox only; live payments are not enabled.')
if DARAJA_SANDBOX_ENABLED:
    from urllib.parse import urlsplit
    callback_origin = urlsplit(DARAJA_CALLBACK_BASE_URL)
    if (not all((DARAJA_CONSUMER_KEY, DARAJA_CONSUMER_SECRET, DARAJA_SHORTCODE, DARAJA_PASSKEY))
            or callback_origin.scheme != 'https' or not callback_origin.hostname
            or callback_origin.username or callback_origin.password or callback_origin.path
            or callback_origin.query or callback_origin.fragment):
        raise ImproperlyConfigured('Daraja sandbox requires complete credentials and a public HTTPS callback origin.')
