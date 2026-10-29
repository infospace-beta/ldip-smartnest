"""Verify Supabase bearer tokens with Auth; keep authorization in Django."""
import json
import secrets
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID

from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import APIException, AuthenticationFailed
from rest_framework import serializers

from .models import User
from .serializers import UserRegistrationSerializer


class AuthUnavailable(APIException):
    status_code = 503
    default_detail = 'Authentication is temporarily unavailable. Please try again.'


class SupabaseAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return 'Bearer'

    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if not header or header[0].lower() != b'bearer':
            return None
        if len(header) != 2:
            raise AuthenticationFailed('Invalid authorization header.')
        try:
            token = header[1].decode('ascii')
        except UnicodeDecodeError as error:
            raise AuthenticationFailed('Invalid access token.') from error
        if not settings.SUPABASE_URL or not settings.SUPABASE_PUBLISHABLE_KEY:
            raise AuthUnavailable()
        auth_request = Request(
            f'{settings.SUPABASE_URL}/auth/v1/user',
            headers={'apikey': settings.SUPABASE_PUBLISHABLE_KEY, 'Authorization': f'Bearer {token}'},
        )
        try:
            with urlopen(auth_request, timeout=10) as response:
                identity = json.load(response)
        except HTTPError as error:
            if error.code in (401, 403):
                raise AuthenticationFailed('Your session has expired. Please sign in again.') from error
            raise AuthUnavailable() from error
        except (URLError, TimeoutError, ValueError) as error:
            raise AuthUnavailable() from error
        try:
            subject = UUID(identity['id'])
            email = identity['email']
            if not email or not identity.get('email_confirmed_at') or identity.get('is_anonymous'):
                raise ValueError('Verified email is required.')
        except (KeyError, TypeError, ValueError) as error:
            raise AuthenticationFailed('A verified email account is required.') from error
        user = User.objects.filter(supabase_user_id=subject).first()
        if user is None:
            metadata = identity.get('user_metadata')
            user = self.provision(subject, email, metadata if isinstance(metadata, dict) else {})
        if not user.is_active or not user.is_active_user:
            raise AuthenticationFailed('This account has been disabled.')
        return user, token

    def provision(self, subject, email, metadata):
        # Never link by email or take roles/access flags from editable user_metadata.
        if User.objects.filter(email__iexact=email).exists():
            raise AuthenticationFailed('Ask an administrator to link your existing SmartNest account to Supabase.')
        data = {
            'email': email,
            'username': f"{str(metadata.get('username') or 'Tenant')[:100]}.{subject.hex[:12]}",
            'password': secrets.token_urlsafe(48),
            'role': 'tenant',
            'phone': metadata.get('phone', ''),
            'consent': metadata.get('consent') is True,
        }
        if metadata.get('invitation_token'):
            data['invitation_token'] = metadata['invitation_token']
        try:
            with transaction.atomic():
                serializer = UserRegistrationSerializer(data=data)
                serializer.is_valid(raise_exception=True)
                user = serializer.save(supabase_user_id=subject)
                user.set_unusable_password()
                user.save(update_fields=['password'])
                return user
        except serializers.ValidationError as error:
            # A concurrent first request may have already provisioned this UUID.
            user = User.objects.filter(supabase_user_id=subject).first()
            if user:
                return user
            raise AuthenticationFailed(error.detail) from error
        except IntegrityError as error:
            user = User.objects.filter(supabase_user_id=subject).first()
            if user:
                return user
            raise AuthenticationFailed('Account provisioning failed. Please contact your manager.') from error
