"""Coordinate backups with API mutations and the automation worker."""
from contextlib import contextmanager
import time
from django.db import connection
from django.http import JsonResponse

LOCK_ID = 824710621


class BackupInProgress(Exception):
    pass


@contextmanager
def application_lock(exclusive=False, wait_seconds=0):
    if connection.vendor != 'postgresql':
        yield
        return
    suffix = '' if exclusive else '_shared'
    acquired = False
    try:
        deadline = time.monotonic() + max(0, wait_seconds)
        while True:
            with connection.cursor() as cursor:
                cursor.execute(f'SELECT pg_try_advisory_lock{suffix}(%s)', [LOCK_ID])
                acquired = cursor.fetchone()[0]
            if acquired:
                break
            if time.monotonic() >= deadline:
                raise BackupInProgress('A backup or application update is in progress; retry later.')
            time.sleep(min(0.25, max(0, deadline - time.monotonic())))
        yield
    finally:
        if acquired:
            with connection.cursor() as cursor:
                cursor.execute(f'SELECT pg_advisory_unlock{suffix}(%s)', [LOCK_ID])


class BackupCoordinationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in ('GET', 'HEAD', 'OPTIONS') or not request.path.startswith(('/api/', '/admin/')):
            return self.get_response(request)
        try:
            with application_lock():
                return self.get_response(request)
        except BackupInProgress:
            response = JsonResponse({'detail': 'SmartNest is taking a backup. Reading records is still available; try this change again shortly.'}, status=503)
            response['Retry-After'] = '30'
            return response
