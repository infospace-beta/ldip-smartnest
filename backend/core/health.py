from datetime import datetime
from django.conf import settings
from django.db import connection
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(['GET'])
@permission_classes([AllowAny])
def readiness(request):
    healthy = True
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            healthy = cursor.fetchone()[0] == 1
        seen = datetime.fromisoformat(settings.AUTOMATION_HEARTBEAT_PATH.read_text(encoding='utf-8').strip())
        age = (timezone.now() - seen).total_seconds()
        healthy = healthy and 0 <= age <= settings.AUTOMATION_HEARTBEAT_MAX_AGE
    except Exception:
        healthy = False
    response = Response({'status': 'ready' if healthy else 'unavailable'}, status=200 if healthy else 503)
    response['Cache-Control'] = 'no-store'
    return response
