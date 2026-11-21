"""Private S3-compatible media; access remains behind Django permission checks."""
from storages.backends.s3 import S3Storage


class PrivateMediaStorage(S3Storage):
    def url(self, name, *args, **kwargs):
        raise ValueError('Private media must be served through an authorized SmartNest API endpoint.')
