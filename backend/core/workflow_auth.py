import base64
import json
from django.conf import settings


def has_verified_mfa(request):
    # SupabaseAuthentication has already verified this bearer token with Auth.
    if not request or not settings.SUPABASE_AUTH_ENABLED:
        return False
    try:
        payload = request.auth.split('.')[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        return claims.get('sub') == str(request.user.supabase_user_id) and claims.get('aal') == 'aal2'
    except (AttributeError, ValueError, IndexError, TypeError):
        return False


def requires_mfa(request):
    return bool(request and settings.SUPABASE_AUTH_ENABLED
                and request.user.mfa_enabled and not has_verified_mfa(request))
