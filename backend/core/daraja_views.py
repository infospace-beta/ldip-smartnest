from datetime import timedelta
from decimal import Decimal, InvalidOperation
import re
from django.conf import settings
from django.db import transaction, IntegrityError
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from .daraja import DarajaSandbox, DarajaUnavailable
from .models import Tenant, SandboxPaymentAttempt
from .views import SmartNestAuthenticated


class PaymentThrottle(UserRateThrottle):
    rate = '6/minute'
    scope = 'daraja_sandbox'


class InitiateSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=16)
    idempotency_key = serializers.UUIDField()

    def validate_phone(self, value):
        value = value.strip().replace(' ', '')
        if value.startswith('+'):
            value = value[1:]
        if value.startswith('0'):
            value = '254' + value[1:]
        if not re.fullmatch(r'254[17][0-9]{8}', value):
            raise serializers.ValidationError('Use a Kenyan mobile number such as +254712345678.')
        return value


def rent_amount(tenant):
    try:
        amount = Decimal(tenant.rent.replace(',', '').strip())
        if not amount.is_finite() or amount <= 0 or amount > 999999 or amount != amount.to_integral_value():
            raise ValueError()
        return amount
    except (InvalidOperation, ValueError):
        raise serializers.ValidationError({'rent':'Your manager must configure a positive whole-shilling rent amount before a sandbox test.'}) from None


def attempt_data(attempt):
    return {'id':str(attempt.pk), 'amount':str(attempt.amount), 'status':attempt.status,
        'callback_received':attempt.callback_received, 'created_at':attempt.created_at,
        'sandbox':True, 'records_real_payment':False}


def own_tenant(user):
    if user.role != 'tenant':
        return None
    return Tenant.objects.filter(user=user, status__in=['active','expiring']).order_by('-pk').first()


@api_view(['GET', 'POST'])
@permission_classes([SmartNestAuthenticated])
@throttle_classes([PaymentThrottle])
def sandbox_payments(request):
    tenant = own_tenant(request.user)
    if tenant is None:
        return Response({'detail':'An active linked tenancy is required.'}, status=403)
    if request.method == 'GET':
        try:
            amount = str(rent_amount(tenant))
        except serializers.ValidationError:
            amount = None
        return Response({'enabled':settings.DARAJA_SANDBOX_ENABLED, 'sandbox':True, 'amount':amount,
            'attempts':[attempt_data(a) for a in SandboxPaymentAttempt.objects.filter(requested_by=request.user).order_by('-created_at')[:20]]})
    if not settings.DARAJA_SANDBOX_ENABLED:
        return Response({'detail':'Daraja sandbox is awaiting credentials and a public HTTPS callback.'}, status=503)
    serializer = InitiateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    with transaction.atomic():
        tenant = Tenant.objects.select_for_update().get(pk=tenant.pk)
        existing = SandboxPaymentAttempt.objects.filter(requested_by=request.user, idempotency_key=values['idempotency_key']).first()
        if existing:
            if existing.phone != values['phone']:
                return Response({'detail':'This request key was already used for a different phone.'}, status=409)
            return Response(attempt_data(existing))
        recent = SandboxPaymentAttempt.objects.filter(tenant=tenant,
            status__in=['initializing','pending','querying','unknown'], created_at__gt=timezone.now()-timedelta(minutes=2)).first()
        if recent:
            return Response({'detail':'A recent sandbox request is still pending. Check its status before starting another.'}, status=409)
        attempt = SandboxPaymentAttempt.objects.create(requested_by=request.user, tenant=tenant,
            phone=values['phone'], amount=rent_amount(tenant), idempotency_key=values['idempotency_key'])
    try:
        result = DarajaSandbox().start(attempt)
        if str(result.get('ResponseCode')) != '0':
            attempt.status = 'sandbox_failed'
        elif all(isinstance(result.get(k), str) and 0 < len(result[k]) <= 128 for k in ('CheckoutRequestID','MerchantRequestID')):
            attempt.checkout_request_id = result['CheckoutRequestID']
            attempt.merchant_request_id = result['MerchantRequestID']
            attempt.status = 'pending'
        else:
            attempt.status = 'unknown'
    except DarajaUnavailable:
        # The provider may have received the request. Never automatically send it again.
        attempt.status = 'unknown'
    try:
        with transaction.atomic():
            attempt.save(update_fields=['status','checkout_request_id','merchant_request_id'])
    except IntegrityError:
        attempt.checkout_request_id=None
        attempt.status='unknown'
        attempt.save(update_fields=['status','checkout_request_id','merchant_request_id'])
    return Response(attempt_data(attempt), status=202)


@api_view(['POST'])
@permission_classes([SmartNestAuthenticated])
@throttle_classes([PaymentThrottle])
def sandbox_query(request, pk):
    if not settings.DARAJA_SANDBOX_ENABLED:
        return Response({'detail':'Daraja sandbox is unavailable.'}, status=503)
    with transaction.atomic():
        attempt = SandboxPaymentAttempt.objects.select_for_update().filter(pk=pk,requested_by=request.user).first()
        if attempt is None:
            return Response({'detail':'Not found.'}, status=404)
        if attempt.status in ('sandbox_success','sandbox_failed','querying') or not attempt.checkout_request_id:
            return Response(attempt_data(attempt))
        attempt.status = 'querying'; attempt.save(update_fields=['status'])
    try:
        result = DarajaSandbox().query(attempt)
        if result.get('CheckoutRequestID') not in (None, attempt.checkout_request_id):
            attempt.status = 'unknown'
        elif isinstance(result.get('ResultCode'), (int,str)) and str(result['ResultCode']).isdigit():
            attempt.status = 'sandbox_success' if str(result['ResultCode']) == '0' else 'sandbox_failed'
        else:
            attempt.status = 'pending'
    except DarajaUnavailable:
        attempt.status = 'pending'
    attempt.save(update_fields=['status'])
    # This sandbox feature never creates Payment objects or changes rent balances.
    return Response(attempt_data(attempt))


@api_view(['POST'])
@permission_classes([AllowAny])
def sandbox_callback(request, pk, secret):
    if not settings.DARAJA_SANDBOX_ENABLED:
        return Response({'detail':'Not found.'},status=404)
    if not isinstance(request.data, dict):
        return Response({'detail':'Invalid callback.'},status=400)
    body = request.data.get('Body')
    callback = body.get('stkCallback') if isinstance(body,dict) else None
    if not isinstance(callback,dict):
        return Response({'detail':'Invalid callback.'},status=400)
    with transaction.atomic():
        attempt = SandboxPaymentAttempt.objects.select_for_update().filter(pk=pk,callback_secret=secret).first()
        if (attempt is None or not attempt.checkout_request_id
                or callback.get('CheckoutRequestID') != attempt.checkout_request_id
                or callback.get('MerchantRequestID') != attempt.merchant_request_id):
            return Response({'detail':'Not found.'},status=404)
        attempt.callback_received = True
        attempt.save(update_fields=['callback_received'])
    # An opaque callback URL is not a provider signature. Callback claims alone
    # never confirm even a sandbox result; only the authenticated query can do so.
    return Response({'ResultCode':0,'ResultDesc':'Callback received; provider query required.'})
