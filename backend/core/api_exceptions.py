from django.db.models.deletion import ProtectedError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(error, context):
    if isinstance(error, ProtectedError):
        return Response({'detail': 'This change would remove retained tenancy history. Record a move-out or disable access instead of deleting the record.'}, status=409)
    return drf_exception_handler(error, context)
