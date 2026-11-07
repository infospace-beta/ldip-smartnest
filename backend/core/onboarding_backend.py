import hashlib
from datetime import timedelta

from django.db import transaction, IntegrityError
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import AccountInvitation, Property, Tenant, Unit, TenancyEvent, User
from .serializers import TenantSerializer, validate_image_upload
from .invitation_tokens import invitation_token
from .views import SmartNestAuthenticated, staff_unit_ids


class CheckInInput(serializers.Serializer):
    account_email = serializers.EmailField(required=False, allow_blank=True)
    name = serializers.CharField(max_length=200)
    phone = serializers.CharField(max_length=20)
    lease_end = serializers.DateField()
    rent = serializers.CharField(max_length=50)
    notes = serializers.CharField(required=False, allow_blank=True)
    evidence_upload = serializers.FileField(required=False)

    def validate_evidence_upload(self, value):
        return validate_image_upload(value, 'Handover photos')


@api_view(['POST'])
@permission_classes([SmartNestAuthenticated])
def check_in_unit(request, pk, unit_pk):
    if request.user.role not in ('manager', 'staff'):
        return Response(status=403)
    allowed = Unit.objects.filter(pk=unit_pk, property_id=pk)
    if request.user.role == 'manager':
        allowed = allowed.filter(property__owner=request.user)
    else:
        allowed = allowed.filter(pk__in=staff_unit_ids(request.user))
    if not allowed.exists():
        return Response({'error': 'Unit not found.'}, status=404)
    serializer = CheckInInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    with transaction.atomic():
        # Use one lock order for all move events: property, unit, tenant.
        prop = Property.objects.select_for_update().get(pk=pk)
        unit = Unit.objects.select_for_update().get(pk=unit_pk)
        if unit.status != 'vacant':
            return Response({'error': 'This unit is already occupied. Refresh the property to continue.'}, status=409)
        if Tenant.objects.filter(unit=unit, status__in=['active', 'expiring']).exists():
            return Response({'error': 'This unit already has an active tenant.'}, status=409)
        account = None
        if values.get('account_email'):
            # Serialize concurrent attempts to attach the same returning account.
            account = User.objects.select_for_update().filter(email__iexact=values['account_email']).first()
            account = TenantSerializer().validate_account_email(values['account_email'])
        tenant = Tenant.objects.create(
            property=prop, unit=unit, name=values['name'], phone=values['phone'],
            lease_end=values['lease_end'], rent=values['rent'], status='active',
            user=account,
        )
        TenancyEvent.objects.create(
            tenant=tenant, unit=unit, action='check_in', recorded_by=request.user,
            notes=values.get('notes', ''), evidence_photo=values.get('evidence_upload', ''),
        )
        unit.status = 'occupied'
        unit.tenant = tenant.name
        unit.rent = tenant.rent
        unit.save(update_fields=['status', 'tenant', 'rent'])
        if account:
            account.portal_access_granted = True
            account.save(update_fields=['portal_access_granted'])
        prop.total_units = prop.units.count()
        prop.occupied_units = prop.units.filter(status='occupied').count()
        prop.status = 'leased' if prop.occupied_units else 'vacant'
        prop.save(update_fields=['total_units', 'occupied_units', 'status'])
    return Response(TenantSerializer(tenant).data, status=status.HTTP_201_CREATED)


class InvitationInput(serializers.Serializer):
    property = serializers.PrimaryKeyRelatedField(queryset=Property.objects.all(),required=False,allow_null=True)
    unit = serializers.PrimaryKeyRelatedField(queryset=Unit.objects.all(),required=False,allow_null=True)
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=['manager', 'staff', 'maintenance'])

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('This email already has an account. Use the existing account controls.')
        return value


@api_view(['POST'])
@permission_classes([SmartNestAuthenticated])
def account_invitations(request):
    if request.user.role not in ('admin', 'manager'):
        return Response(status=403)
    serializer = InvitationInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    role = values['role']
    prop=values.get('property');unit=values.get('unit')
    if unit and (not prop or unit.property_id!=prop.pk):
        return Response({'error':'Choose a unit within the selected property.'},status=400)
    if prop and request.user.role=='manager' and prop.owner_id!=request.user.pk:
        return Response(status=403)

    if not ((request.user.role == 'admin' and role == 'manager') or
            (request.user.role == 'manager' and role in ('staff', 'maintenance'))):
        return Response(status=403)
    try:
        with transaction.atomic():
            # Serializes invitations for a recipient even across different inviters.
            # Locking the inviter also protects the common repeated-click case.
            User.objects.select_for_update().get(pk=request.user.pk)
            invitation = AccountInvitation.objects.select_for_update().filter(email=values['email']).first()
            if invitation and (invitation.created_by_id != request.user.pk or invitation.role != role):
                return Response({'error': 'An invitation already exists for this recipient.'}, status=409)
            if invitation and invitation.accepted_at:
                return Response({'error': 'This invitation has already been accepted.'}, status=409)
            if not invitation:
                invitation = AccountInvitation(email=values['email'], role=role, created_by=request.user)
            if not invitation.pk or not invitation.expires_at or invitation.expires_at <= timezone.now():
                invitation.expires_at = timezone.now() + timedelta(days=7)
            invitation.property=prop
            invitation.unit=unit
            invitation.name = values['name']
            invitation.phone = values.get('phone', '')
            token = invitation_token('account', invitation.id, invitation.expires_at)
            invitation.token_digest = hashlib.sha256(token.encode()).hexdigest()
            invitation.save()
    except IntegrityError:
        return Response({'error': 'An invitation already exists for this recipient. Refresh and try again.'}, status=409)
    return Response({'token': token, 'email': invitation.email, 'expires_at': invitation.expires_at}, status=201)


@api_view(['GET'])
@permission_classes([AllowAny])
def account_invitation_details(request, token):
    invitation = AccountInvitation.objects.select_related('created_by').filter(
        token_digest=hashlib.sha256(token.encode()).hexdigest(),
        accepted_at__isnull=True, expires_at__gt=timezone.now(),
    ).first()
    if not invitation or not invitation.issuer_valid():
        return Response({'error': 'This invitation is invalid or expired.'}, status=404)
    response = Response({'email': invitation.email, 'name': invitation.name, 'phone': invitation.phone,
                         'role': invitation.role, 'expires_at': invitation.expires_at})
    response['Cache-Control'] = 'no-store'
    return response
