"""Twilio notification outbox. Supabase owns sign-in OTP delivery separately."""
import base64
from datetime import timedelta
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException


def verified_phone(token, subject):
    try:
        request = Request(f'{settings.SUPABASE_URL}/auth/v1/user', headers={
            'apikey': settings.SUPABASE_PUBLISHABLE_KEY, 'Authorization': f'Bearer {token}',
        })
        with urlopen(request, timeout=10) as response:
            identity = json.load(response)
        if identity.get('id') != str(subject):
            return ''
        raw = identity.get('phone', '')
        if not isinstance(raw, str):
            return ''
        phone = raw if raw.startswith('+') else f'+{raw}'
        if identity.get('phone_confirmed_at') and re.fullmatch(r'\+[1-9][0-9]{7,14}', phone):
            return phone
    except (HTTPError, URLError, ValueError, TimeoutError):
        error = APIException('Phone verification could not be checked. Please try again later.')
        error.status_code = 503
        raise error from None
    return ''


def queue_notice_sms(sender, instance, action, reverse, pk_set, **kwargs):
    if action != 'post_add' or not settings.SMARTNEST_SMS_ENABLED:
        return
    from .models import Notice, User, SMSNotification
    notices = Notice.objects.filter(pk__in=pk_set) if reverse else [instance]
    for notice in notices:
        users = [instance] if reverse else User.objects.filter(pk__in=pk_set)
        for user in users:
            if user.sms_notifications and user.sms_verified_phone and user.is_active and user.is_active_user:
                SMSNotification.objects.get_or_create(notice=notice, user=user)


def deliver_notifications(limit=50, dry_run=False):
    from .models import SMSNotification
    result = {'accepted': 0, 'failed': 0, 'unknown': 0, 'skipped': 0}
    if not settings.SMARTNEST_SMS_ENABLED:
        return {**result, 'disabled': True}
    if dry_run:
        return {**result, 'pending': SMSNotification.objects.filter(status='pending').count(), 'dry_run': True}
    if not all([settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_MESSAGING_SERVICE_SID]):
        raise RuntimeError('SMS delivery is enabled but Twilio credentials are missing.')
    for _ in range(limit):
        with transaction.atomic():
            item = SMSNotification.objects.select_for_update(skip_locked=True).filter(status='pending').select_related('user').order_by('pk').first()
            if item is None:
                break
            user = item.user
            if (not user.sms_notifications or not user.is_active or not user.is_active_user
                    or not user.sms_verified_phone or item.created_at < timezone.now() - timedelta(days=1)):
                item.status = 'skipped'; item.save(update_fields=['status']); result['skipped'] += 1
                continue
            item.status = 'sending'; item.save(update_fields=['status'])
            phone = user.sms_verified_phone
        credentials = base64.b64encode(f'{settings.TWILIO_ACCOUNT_SID}:{settings.TWILIO_AUTH_TOKEN}'.encode()).decode()
        request = Request(f'https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json',
            data=urlencode({'To': phone, 'MessagingServiceSid': settings.TWILIO_MESSAGING_SERVICE_SID,
                'Body': f'SmartNest: You have a new property notification. Sign in to view it: {settings.FRONTEND_URL}/dashboard/notices'}).encode(),
            headers={'Authorization': f'Basic {credentials}', 'Content-Type': 'application/x-www-form-urlencoded'}, method='POST')
        # Ambiguous network outcomes are never automatically retried: a charge or delivery may have occurred.
        try:
            with urlopen(request, timeout=10) as response:
                data = json.load(response)
            if not isinstance(data, dict) or not isinstance(data.get('sid'), str) or not data['sid'].startswith('SM'):
                raise ValueError('Missing provider message ID.')
            item.status = 'accepted'; item.provider_sid = data['sid']
        except HTTPError as error:
            item.status = 'failed' if 400 <= error.code < 500 else 'unknown'
        except (URLError, TimeoutError, ValueError, OSError):
            item.status = 'unknown'
        item.save(update_fields=['status', 'provider_sid'])
        result[item.status] += 1
    return result
