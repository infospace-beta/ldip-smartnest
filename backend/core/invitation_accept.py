"""Accept an invitation using an existing, provider-verified sign-in identity."""
from types import SimpleNamespace
from django.conf import settings
from rest_framework import serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from .models import User
from .serializers import UserSerializer
from .supabase_auth import SupabaseAuthentication, AuthUnavailable


class InvitationIdentityAuthentication(SupabaseAuthentication):
    """Limited to this endpoint; this identity has no Django operational role."""
    def authenticate(self,request):
        if not settings.SUPABASE_AUTH_ENABLED:
            raise AuthUnavailable()
        verified=self.verified_identity(request)
        if verified is None:
            return None
        subject,email,identity,token=verified
        return SimpleNamespace(pk=subject,subject=subject,email=email,identity=identity,is_authenticated=True),token


class InvitationAcceptThrottle(UserRateThrottle):
    rate='12/hour'
    scope='accept_invitation'


class AcceptanceInput(serializers.Serializer):
    account_invitation_token=serializers.CharField(required=False,max_length=512)
    invitation_token=serializers.CharField(required=False,max_length=512)
    consent=serializers.BooleanField()

    def validate(self,data):
        if bool(data.get('account_invitation_token'))==bool(data.get('invitation_token')):
            raise serializers.ValidationError('Supply exactly one invitation code.')
        if not data['consent']:
            raise serializers.ValidationError('Account consent is required.')
        return data


@api_view(['POST'])
@authentication_classes([InvitationIdentityAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([InvitationAcceptThrottle])
def accept_invitation(request):
    serializer=AcceptanceInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    values=serializer.validated_data
    identity=request.user
    if User.objects.filter(supabase_user_id=identity.subject).exists():
        return Response({'detail':'This sign-in already has a SmartNest account. Sign in normally; ask an administrator to review any role change.'},status=409)
    metadata=identity.identity.get('user_metadata')
    metadata=dict(metadata) if isinstance(metadata,dict) else {}
    # Ignore any old invitation in editable metadata. The explicit submitted code
    # is validated against the provider-confirmed email and a trusted issuer.
    metadata.pop('account_invitation_token',None)
    metadata.pop('invitation_token',None)
    metadata.update(values)
    user=SupabaseAuthentication().provision(identity.subject,identity.email,metadata)
    if not user.is_active or not user.is_active_user:
        raise AuthenticationFailed('This account has been disabled.')
    request.user=user
    return Response(UserSerializer(user,context={'request':request}).data,status=201)
