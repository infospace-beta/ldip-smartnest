import os
from urllib.parse import urlsplit
from django.core.exceptions import ImproperlyConfigured


def configured_storages(backend):
    storage = {'BACKEND': 'django.core.files.storage.FileSystemStorage'}
    if backend == 's3':
        required = ['SMARTNEST_S3_ENDPOINT', 'SMARTNEST_S3_ACCESS_KEY', 'SMARTNEST_S3_SECRET_KEY', 'SMARTNEST_MEDIA_BUCKET']
        if any(not os.getenv(key) for key in required):
            raise ImproperlyConfigured('Private object storage requires its endpoint, server credentials and media bucket. Values are hidden.')
        endpoint = urlsplit(os.environ['SMARTNEST_S3_ENDPOINT'])
        if endpoint.scheme != 'https' or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
            raise ImproperlyConfigured('Private object storage requires an HTTPS endpoint without embedded credentials.')
        from botocore.config import Config
        storage = {'BACKEND': 'core.private_storage.PrivateMediaStorage', 'OPTIONS': {
            'access_key': os.environ['SMARTNEST_S3_ACCESS_KEY'], 'secret_key': os.environ['SMARTNEST_S3_SECRET_KEY'],
            'bucket_name': os.environ['SMARTNEST_MEDIA_BUCKET'], 'endpoint_url': os.environ['SMARTNEST_S3_ENDPOINT'],
            'region_name': os.getenv('SMARTNEST_S3_REGION', 'ap-south-1'), 'default_acl': None,
            'file_overwrite': False, 'custom_domain': None, 'querystring_auth': True, 'querystring_expire': 60,
            'object_parameters': {'CacheControl': 'private, no-store'}, 'max_memory_size': 1024 * 1024,
            'client_config': Config(signature_version='s3v4', s3={'addressing_style': 'path'}, request_checksum_calculation='when_required', response_checksum_validation='when_required', connect_timeout=10, read_timeout=30, retries={'max_attempts': 2}),
        }}
    elif backend != 'filesystem':
        raise ImproperlyConfigured('SMARTNEST_MEDIA_BACKEND must be filesystem or s3.')
    return {'default': storage, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
