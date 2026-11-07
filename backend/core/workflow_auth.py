import base64
import json
from django.conf import settings
def requires_mfa(request):
    if not request or not settings.SUPABASE_AUTH_ENABLED or request.user.role not in ('admin','manager'):return False
    # SupabaseAuthentication has already verified this bearer token with /auth/v1/user.
    try:
        token=request.auth
        payload=token.split('.')[1]
        claims=json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))
        return claims.get('sub')!=str(request.user.supabase_user_id) or claims.get('aal')!='aal2'
    except (AttributeError,ValueError,IndexError,TypeError):return True
