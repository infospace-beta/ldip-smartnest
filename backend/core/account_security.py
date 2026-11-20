"""Private, self-service security preferences; provider identities remain authoritative."""
from datetime import timedelta
import hashlib
import hmac
import secrets
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from .models import User
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import AuthenticationFailed


class SecurityAuthenticated(IsAuthenticated):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if not request.user.is_active or not request.user.is_active_user:
            raise AuthenticationFailed('This account has been disabled.')
        return True
from .workflow_auth import has_verified_mfa, requires_mfa


class SecurityThrottle(UserRateThrottle):
    rate = '20/hour'
    scope = 'account_security'


def summary(user):
    return {
        'mfa_enabled': user.mfa_enabled,
        'security_prompt_dismissed': user.security_prompt_dismissed,
        'secondary_email': user.secondary_email,
        'secondary_email_verified': bool(user.secondary_email_verified_at),
        'pending_secondary_email': user.pending_secondary_email,
        'sms_notifications': user.sms_notifications,
        'sms_available': settings.SMARTNEST_SMS_ENABLED,
        'email_available': settings.EMAIL_BACKEND != 'django.core.mail.backends.console.EmailBackend'
            and (bool(settings.EMAIL_HOST) or settings.EMAIL_BACKEND == 'django.core.mail.backends.locmem.EmailBackend'),
    }


def code_digest(user_id, email, code):
    # A keyed digest prevents offline brute force of the six-digit code.
    return hmac.new(settings.SECRET_KEY.encode(), f'{user_id}:{email}:{code}'.encode(), hashlib.sha256).hexdigest()


@api_view(['GET', 'POST'])
@permission_classes([SecurityAuthenticated])
@throttle_classes([SecurityThrottle])
def security_settings(request):
    if request.method == 'GET':
        return Response(summary(request.user))
    if requires_mfa(request):
        raise PermissionDenied('Verify your authenticator before changing security settings.')
    action = request.data.get('action')
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=request.user.pk)
        if action == 'dismiss_recommendation':
            user.security_prompt_dismissed = True
            user.save(update_fields=['security_prompt_dismissed'])
        elif action in ('enable_mfa', 'disable_mfa'):
            if not settings.SUPABASE_AUTH_ENABLED or not has_verified_mfa(request):
                raise PermissionDenied('Verify an authenticator code before enabling or disabling two-step verification.')
            user.mfa_enabled = action == 'enable_mfa'
            user.security_prompt_dismissed = True
            user.save(update_fields=['mfa_enabled', 'security_prompt_dismissed'])
        elif action == 'request_secondary_email':
            email = serializers.EmailField().run_validation(request.data.get('email'))
            if email.casefold() == user.email.casefold():
                raise serializers.ValidationError({'email': 'Use a different address from your sign-in email.'})
            if not summary(user)['email_available']:
                return Response({'detail': 'Backup email verification is unavailable until the email delivery service is configured.'}, status=503)
            if user.secondary_code_expires_at and user.secondary_code_expires_at > timezone.now() + timedelta(minutes=9):
                return Response({'detail': 'Wait one minute before requesting another code.'}, status=429)
            code = f'{secrets.randbelow(1_000_000):06d}'
            try:
                delivered = send_mail('Verify your SmartNest backup email',
                    f'Your verification code is {code}. It expires in 10 minutes. If you did not request this, ignore this email.',
                    settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
                if delivered != 1:
                    raise RuntimeError('Email was not accepted.')
            except Exception:
                return Response({'detail': 'The verification email could not be sent. Please try again later.'}, status=503)
            user.pending_secondary_email = email
            user.secondary_code_digest = code_digest(user.pk, email, code)
            user.secondary_code_expires_at = timezone.now() + timedelta(minutes=10)
            user.secondary_code_attempts = 0
            user.save(update_fields=['pending_secondary_email', 'secondary_code_digest', 'secondary_code_expires_at', 'secondary_code_attempts'])
        elif action == 'confirm_secondary_email':
            code = request.data.get('code', '')
            if not isinstance(code, str) or len(code) != 6 or not code.isascii() or not code.isdigit():
                raise serializers.ValidationError({'code': 'Enter the six-digit email code.'})
            if (not user.pending_secondary_email or not user.secondary_code_digest
                    or not user.secondary_code_expires_at or user.secondary_code_expires_at <= timezone.now()
                    or user.secondary_code_attempts >= 5):
                return Response({'detail': 'This code is expired or unavailable. Request a new code.'}, status=400)
            user.secondary_code_attempts += 1
            user.save(update_fields=['secondary_code_attempts'])
            if not secrets.compare_digest(user.secondary_code_digest, code_digest(user.pk, user.pending_secondary_email, code)):
                return Response({'detail': 'The verification code is incorrect.'}, status=400)
            user.secondary_email = user.pending_secondary_email
            user.secondary_email_verified_at = timezone.now()
            user.pending_secondary_email = ''
            user.secondary_code_digest = ''
            user.secondary_code_expires_at = None
            user.save(update_fields=['secondary_email', 'secondary_email_verified_at', 'pending_secondary_email', 'secondary_code_digest', 'secondary_code_expires_at'])
        elif action == 'remove_secondary_email':
            user.secondary_email = user.pending_secondary_email = user.secondary_code_digest = ''
            user.secondary_email_verified_at = user.secondary_code_expires_at = None
            user.save(update_fields=['secondary_email', 'pending_secondary_email', 'secondary_code_digest', 'secondary_email_verified_at', 'secondary_code_expires_at'])
        elif action == 'sms_notifications':
            enabled = serializers.BooleanField().run_validation(request.data.get('enabled'))
            if enabled and not settings.SMARTNEST_SMS_ENABLED:
                return Response({'detail': 'SMS delivery is not configured yet.'}, status=503)
            # Only a phone independently verified by Supabase can receive notifications.
            if enabled:
                from .sms import verified_phone
                phone = verified_phone(request.auth, user.supabase_user_id)
                if not phone:
                    raise serializers.ValidationError({'phone': 'Verify your phone number in Account security first.'})
                user.sms_verified_phone = phone
            else:
                user.sms_verified_phone = ''
            user.sms_notifications = enabled
            user.save(update_fields=['sms_notifications', 'sms_verified_phone'])
        else:
            raise serializers.ValidationError({'action': 'Unknown security action.'})
    return Response(summary(user))
