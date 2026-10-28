import hashlib
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone
from uuid import uuid4
from .models import (
    User, Property, Unit, Tenant, Payment, Notice, MaintenanceJob, Staff, Expense,
    UnitInspection, TenancyEvent, Conversation, TenantInvitation,
)
from .serializers import (
    UserSerializer, UserRegistrationSerializer, LoginSerializer,
    PropertySerializer, StaffPropertySerializer,
    TenantPropertySerializer, UnitSerializer, TenantSerializer,
    PaymentSerializer, NoticeSerializer, MaintenanceJobSerializer,
    StaffSerializer, DashboardStatsSerializer, ExpenseSerializer,
    UnitInspectionSerializer, UserProfileSerializer, UserAccessSerializer,
    TeamMemberOnboardingSerializer, TenantInvitationSerializer,
    CommunicationContactSerializer, ConversationSerializer, MessageSerializer,
    StartConversationSerializer, CreateMessageSerializer, TenancyEventSerializer,
    MaintenanceVendorUpdateSerializer,
)

User = get_user_model()


class SmartNestAuthenticated(IsAuthenticated):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if not request.user.is_active_user:
            raise AuthenticationFailed('This account has been disabled.')
        if request.user.role == 'tenant':
            if (
                not request.user.portal_access_granted
                or not Tenant.objects.filter(user=request.user).exists()
            ):
                raise AuthenticationFailed('Your manager must link your tenant record before you can sign in.')
        return True


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


def has_role(user, *roles):
    return user.role in roles


def tenant_record(user):
    return Tenant.objects.filter(user=user).first()


def apply_staff_cluster(queryset, user, lookup):
    if user.role != 'staff':
        return queryset
    unit_ids = user.assigned_units.values_list('id', flat=True)
    if not unit_ids.exists():
        return queryset.none()
    model_lookups = {
        Property: 'units__id__in',
        Unit: 'id__in',
        Tenant: 'unit_id__in',
        Payment: 'tenant__unit_id__in',
        MaintenanceJob: 'unit_id__in',
        Expense: 'property__units__id__in',
        UnitInspection: 'unit_id__in',
    }
    unit_lookup = model_lookups.get(queryset.model)
    if not unit_lookup:
        return queryset.none()
    return queryset.filter(**{unit_lookup: unit_ids}).distinct()


def can_contact(sender, recipient):
    if sender.pk == recipient.pk or not recipient.is_active or not recipient.is_active_user:
        return False
    if sender.role == 'admin':
        return True
    if sender.role == 'manager':
        return recipient.role != 'admin'
    if sender.role == 'tenant':
        tenant = tenant_record(sender)
        if not tenant or not tenant.unit_id:
            return False
        if recipient.role == 'manager':
            return True
        if recipient.role == 'staff':
            return recipient.assigned_units.filter(pk=tenant.unit_id).exists()
        if recipient.role == 'maintenance':
            return MaintenanceJob.objects.filter(
                reported_by_user=sender,
                assignee__in=[recipient.username, recipient.email],
            ).exists()
        return False
    if sender.role == 'staff':
        assigned_unit_ids = sender.assigned_units.values_list('id', flat=True)
        if recipient.role == 'manager':
            return True
        if recipient.role == 'tenant':
            return Tenant.objects.filter(user=recipient, unit_id__in=assigned_unit_ids).exists()
        if recipient.role == 'maintenance':
            return MaintenanceJob.objects.filter(
                unit_id__in=assigned_unit_ids,
                assignee__in=[recipient.username, recipient.email],
            ).exists()
        return False
    if sender.role == 'maintenance':
        jobs = MaintenanceJob.objects.filter(assignee__in=[sender.username, sender.email])
        if recipient.role == 'manager':
            return jobs.exists()
        if recipient.role == 'staff':
            return jobs.filter(unit_id__in=recipient.assigned_units.values_list('id', flat=True)).exists()
        if recipient.role == 'tenant':
            return jobs.filter(reported_by_user=recipient).exists()
    return False


def forbidden():
    return Response({'error': 'You do not have permission to perform this action.'}, status=status.HTTP_403_FORBIDDEN)


@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    with transaction.atomic():
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            message = (
                'Invitation accepted. Your tenant portal is ready.'
                if user.portal_access_granted
                else 'Account created. Your manager must link your tenant record before you can sign in.'
            )
            return Response({
                'user': UserSerializer(user).data,
                'message': message,
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([SmartNestAuthenticated])
def create_tenant_invitation(request, pk):
    if request.user.role != 'manager':
        return forbidden()
    try:
        tenant = Tenant.objects.get(pk=pk)
    except Tenant.DoesNotExist:
        return Response({'error': 'Tenant not found.'}, status=status.HTTP_404_NOT_FOUND)
    serializer = TenantInvitationSerializer(
        data=request.data,
        context={'request': request, 'tenant': tenant},
    )
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    serializer.save()
    return Response({
        'token': serializer.token,
        'email': tenant.invitation.email,
        'expires_at': tenant.invitation.expires_at,
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([AllowAny])
def tenant_invitation_details(request, token):
    digest = hashlib.sha256(token.encode()).hexdigest()
    invitation = TenantInvitation.objects.select_related('tenant').filter(
        token_digest=digest,
        accepted_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).first()
    if not invitation or invitation.tenant.user_id:
        return Response({'error': 'This tenant invitation is invalid or has expired.'}, status=status.HTTP_404_NOT_FOUND)
    return Response({
        'email': invitation.email,
        'tenant_name': invitation.tenant.name,
        'phone': invitation.tenant.phone,
        'expires_at': invitation.expires_at,
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    serializer = LoginSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.validated_data['user']
        tokens = get_tokens_for_user(user)
        return Response({
            'user': UserSerializer(user).data,
            'tokens': tokens,
        }, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PATCH'])
@permission_classes([SmartNestAuthenticated])
def me(request):
    if request.method == 'GET':
        return Response(UserSerializer(request.user).data)
    serializer = UserProfileSerializer(request.user, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(UserSerializer(serializer.instance).data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PATCH'])
@permission_classes([SmartNestAuthenticated])
def user_access_list(request, pk=None):
    if request.user.role != 'admin':
        return forbidden()
    if pk is not None:
        try:
            target = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        if request.method == 'GET':
            return Response(UserAccessSerializer(target).data)
        serializer = UserAccessSerializer(
            target,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        if serializer.is_valid():
            serializer.save()
            return Response(UserAccessSerializer(serializer.instance).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    if request.method != 'GET':
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)
    users = User.objects.prefetch_related('assigned_units').order_by('username')
    return Response(UserAccessSerializer(users, many=True).data)


@api_view(['GET'])
@permission_classes([SmartNestAuthenticated])
def user_assignment_options(request):
    if request.user.role != 'admin':
        return forbidden()
    units = Unit.objects.select_related('property').order_by('property__name', 'unit_number')
    return Response({
        'units': [
            {
                'id': unit.id,
                'unit_number': unit.unit_number,
                'property_id': unit.property_id,
                'property_name': unit.property.name,
            }
            for unit in units
        ],
    })


@api_view(['POST'])
@permission_classes([SmartNestAuthenticated])
def team_onboarding(request):
    if request.user.role != 'manager':
        return forbidden()
    serializer = TeamMemberOnboardingSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    user = serializer.save()
    return Response(UserAccessSerializer(user).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([SmartNestAuthenticated])
def communication_contacts(request):
    contacts = User.objects.filter(is_active=True, is_active_user=True).exclude(pk=request.user.pk).order_by('username')
    return Response(
        CommunicationContactSerializer(
            [contact for contact in contacts if can_contact(request.user, contact)],
            many=True,
        ).data
    )


@api_view(['GET', 'POST'])
@permission_classes([SmartNestAuthenticated])
def conversations_list(request):
    if request.method == 'GET':
        conversations = Conversation.objects.filter(participants=request.user).distinct()
        return Response(ConversationSerializer(conversations, many=True).data)
    serializer = StartConversationSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    recipient = serializer.validated_data['recipient']
    if not can_contact(request.user, recipient):
        return forbidden()
    with transaction.atomic():
        conversation = Conversation.objects.create(
            subject=serializer.validated_data['subject'],
            created_by=request.user,
        )
        conversation.participants.add(request.user, recipient)
        conversation.messages.create(sender=request.user, body=serializer.validated_data['body'])
    return Response(ConversationSerializer(conversation).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'POST'])
@permission_classes([SmartNestAuthenticated])
def conversation_messages(request, pk):
    try:
        conversation = Conversation.objects.get(pk=pk, participants=request.user)
    except Conversation.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        return Response(MessageSerializer(conversation.messages.select_related('sender'), many=True).data)
    serializer = CreateMessageSerializer(data=request.data)
    if serializer.is_valid():
        message = conversation.messages.create(
            sender=request.user,
            body=serializer.validated_data['body'],
        )
        return Response(MessageSerializer(message).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([SmartNestAuthenticated])
def dashboard_stats(request):
    user = request.user
    tenant = tenant_record(user) if user.role == 'tenant' else None
    if user.role == 'tenant':
        payments = Payment.objects.filter(tenant=tenant) if tenant else Payment.objects.none()
        units = Unit.objects.filter(pk=tenant.unit_id) if tenant and tenant.unit_id else Unit.objects.none()
        data = {
            'total_properties': 1 if tenant else 0,
            'total_tenants': 1 if tenant else 0,
            'rental_income': f'KSh {payments.aggregate(total=Sum("amount"))["total"] or 0:,.0f}',
            'expenses': 'KSh 0',
            'occupied_units': units.filter(status='occupied').count(),
            'vacant_units': units.filter(status='vacant').count(),
            'active_leases': 1 if tenant and tenant.status == 'active' else 0,
        }
        return Response(data)

    if user.role not in ('manager', 'staff'):
        return forbidden()

    properties = apply_staff_cluster(Property.objects.all(), user, 'cluster')
    tenants = apply_staff_cluster(Tenant.objects.all(), user, 'property__cluster')
    units = apply_staff_cluster(Unit.objects.all(), user, 'property__cluster')
    payments = apply_staff_cluster(Payment.objects.all(), user, 'tenant__property__cluster')
    total_properties = properties.count()
    total_tenants = tenants.count()
    total_income = 0
    if user.role == 'manager':
        total_income = payments.aggregate(total=Sum('amount'))['total'] or 0
    occupied_units = units.filter(status='occupied').count()
    vacant_units = units.filter(status='vacant').count()
    active_leases = tenants.filter(status='active').count()

    data = {
        'total_properties': total_properties,
        'total_tenants': total_tenants,
        'rental_income': f'KSh {total_income:,.0f}' if user.role == 'manager' else '',
        'expenses': 'KSh 165,400' if user.role == 'manager' else '',
        'occupied_units': occupied_units,
        'vacant_units': vacant_units,
        'active_leases': active_leases,
    }
    return Response(data)


# Properties
@api_view(['GET', 'POST'])
@permission_classes([SmartNestAuthenticated])
def properties_list(request):
    if request.method == 'GET':
        if request.user.role == 'admin':
            return forbidden()
        if request.user.role not in ('manager', 'staff', 'tenant'):
            return forbidden()
        properties = Property.objects.all()
        if request.user.role == 'tenant':
            tenant = tenant_record(request.user)
            properties = properties.filter(pk=tenant.property_id) if tenant else properties.none()
        properties = apply_staff_cluster(properties, request.user, 'cluster')
        if request.user.role == 'staff':
            serializer_class = StaffPropertySerializer
        elif request.user.role == 'tenant':
            serializer_class = TenantPropertySerializer
        else:
            serializer_class = PropertySerializer
        serializer = serializer_class(properties, many=True, context={'request': request})
        return Response(serializer.data)
    if not has_role(request.user, 'manager'):
        return forbidden()
    serializer = PropertySerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([SmartNestAuthenticated])
def property_detail(request, pk):
    if request.user.role == 'admin' or request.user.role not in ('manager', 'staff', 'tenant'):
        return forbidden()
    try:
        properties = Property.objects.all()
        if request.user.role == 'tenant':
            tenant = tenant_record(request.user)
            properties = properties.filter(pk=tenant.property_id) if tenant else properties.none()
        properties = apply_staff_cluster(properties, request.user, 'cluster')
        prop = properties.get(pk=pk)
    except Property.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        if request.user.role == 'staff':
            serializer_class = StaffPropertySerializer
        elif request.user.role == 'tenant':
            serializer_class = TenantPropertySerializer
        else:
            serializer_class = PropertySerializer
        return Response(serializer_class(prop, context={'request': request}).data)
    elif request.method == 'PUT':
        if not has_role(request.user, 'manager'):
            return forbidden()
        serializer = PropertySerializer(prop, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    elif request.method == 'DELETE':
        if not has_role(request.user, 'manager'):
            return forbidden()
        prop.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# Units
@api_view(['GET', 'POST'])
@permission_classes([SmartNestAuthenticated])
def units_list(request):
    if request.method == 'GET':
        if request.user.role == 'admin':
            return forbidden()
        if request.user.role not in ('manager', 'staff', 'tenant'):
            return forbidden()
        units = Unit.objects.all()
        if request.user.role == 'tenant':
            tenant = tenant_record(request.user)
            units = units.filter(pk=tenant.unit_id) if tenant and tenant.unit_id else units.none()
        units = apply_staff_cluster(units, request.user, 'property__cluster')
        serializer = UnitSerializer(units, many=True)
        return Response(serializer.data)
    if not has_role(request.user, 'manager'):
        return forbidden()
    serializer = UnitSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Tenants
@api_view(['GET', 'POST'])
@permission_classes([SmartNestAuthenticated])
def tenants_list(request):
    if request.method == 'GET':
        if request.user.role == 'admin':
            return forbidden()
        if request.user.role not in ('manager', 'staff', 'tenant'):
            return Response([]) if request.user.role == 'maintenance' else forbidden()
        tenants = Tenant.objects.all()
        if request.user.role == 'tenant':
            tenants = tenants.filter(user=request.user)
        tenants = apply_staff_cluster(tenants, request.user, 'property__cluster')
        serializer = TenantSerializer(tenants, many=True)
        return Response(serializer.data)
    if not has_role(request.user, 'manager'):
        return forbidden()
    serializer = TenantSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Payments
@api_view(['GET', 'POST'])
@permission_classes([SmartNestAuthenticated])
def payments_list(request):
    if request.method == 'GET':
        if request.user.role == 'admin' or request.user.role not in ('manager', 'tenant'):
            return forbidden()
        payments = Payment.objects.all()
        if request.user.role == 'tenant':
            payments = payments.filter(tenant__user=request.user)
        serializer = PaymentSerializer(payments, many=True)
        return Response(serializer.data)
    if not has_role(request.user, 'manager'):
        return forbidden()
    serializer = PaymentSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Notices
@api_view(['GET', 'POST'])
@permission_classes([SmartNestAuthenticated])
def notices_list(request):
    if request.method == 'GET':
        notices = Notice.objects.all()
        serializer = NoticeSerializer(notices, many=True)
        return Response(serializer.data)
    if not has_role(request.user, 'admin', 'manager', 'staff'):
        return forbidden()
    serializer = NoticeSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([SmartNestAuthenticated])
def notices_unread_count(request):
    count = Notice.objects.filter(is_read=False).count()
    return Response({'unread_count': count})


# Maintenance Jobs
@api_view(['GET', 'POST'])
@permission_classes([SmartNestAuthenticated])
def maintenance_list(request):
    if request.method == 'GET':
        if request.user.role not in ('manager', 'staff', 'maintenance', 'tenant'):
            return forbidden()
        jobs = MaintenanceJob.objects.all()
        if request.user.role == 'tenant':
            jobs = jobs.filter(reported_by_user=request.user)
        elif request.user.role == 'maintenance':
            jobs = jobs.filter(assignee__in=[request.user.username, request.user.email])
        jobs = apply_staff_cluster(jobs, request.user, 'property__cluster')
        serializer = MaintenanceJobSerializer(jobs, many=True)
        return Response(serializer.data)
    if request.user.role == 'tenant':
        tenant = tenant_record(request.user)
        if not tenant or not tenant.unit_id:
            return Response({'error': 'A linked tenant and unit record is required to submit a maintenance request.'}, status=status.HTTP_400_BAD_REQUEST)
        payload = {
            'job_id': f'REQ-{uuid4().hex[:10].upper()}',
            'property': tenant.property_id,
            'unit': tenant.unit_id,
            'issue': request.data.get('issue', ''),
            'reported_by': tenant.name,
            'assignee': 'Property management',
            'priority': 'medium',
            'status': 'logged',
            'date': timezone.localdate().isoformat(),
        }
        serializer = MaintenanceJobSerializer(data=payload)
        if serializer.is_valid():
            serializer.save(reported_by_user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    if not has_role(request.user, 'manager', 'staff'):
        return forbidden()
    serializer = MaintenanceJobSerializer(data=request.data)
    if serializer.is_valid():
        if request.user.role == 'staff':
            unit = serializer.validated_data.get('unit')
            if not unit or not request.user.assigned_units.filter(pk=unit.pk).exists():
                return forbidden()
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PATCH'])
@permission_classes([SmartNestAuthenticated])
def maintenance_detail(request, pk):
    if request.user.role not in ('manager', 'staff', 'maintenance', 'tenant'):
        return forbidden()
    jobs = MaintenanceJob.objects.all()
    if request.user.role == 'staff':
        jobs = jobs.filter(unit__in=request.user.assigned_units.all())
    elif request.user.role == 'maintenance':
        jobs = jobs.filter(assignee__in=[request.user.username, request.user.email])
    elif request.user.role == 'tenant':
        jobs = jobs.filter(reported_by_user=request.user)
    try:
        job = jobs.get(pk=pk)
    except MaintenanceJob.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(MaintenanceJobSerializer(job).data)
    if request.user.role == 'maintenance':
        serializer = MaintenanceVendorUpdateSerializer(job, data=request.data, partial=True)
    elif request.user.role == 'manager':
        serializer = MaintenanceJobSerializer(job, data=request.data, partial=True)
    else:
        return forbidden()
    if serializer.is_valid():
        serializer.save()
        return Response(MaintenanceJobSerializer(job).data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'POST'])
@permission_classes([SmartNestAuthenticated])
def tenancy_events(request):
    if request.user.role not in ('manager', 'staff'):
        return forbidden()
    if request.method == 'GET':
        events = TenancyEvent.objects.select_related('tenant', 'unit', 'unit__property', 'recorded_by')
        if request.user.role == 'staff':
            events = events.filter(unit__in=request.user.assigned_units.all())
        return Response(TenancyEventSerializer(events, many=True).data)

    serializer = TenancyEventSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    tenant = serializer.validated_data['tenant']
    unit = serializer.validated_data['unit']
    if request.user.role == 'staff' and not request.user.assigned_units.filter(pk=unit.pk).exists():
        return forbidden()

    with transaction.atomic():
        unit = Unit.objects.select_for_update().get(pk=unit.pk)
        tenant = Tenant.objects.select_for_update().get(pk=tenant.pk)
        if tenant.unit_id != unit.id or tenant.property_id != unit.property_id:
            return Response({'unit': ['Choose the tenant’s assigned unit.']}, status=status.HTTP_400_BAD_REQUEST)
        action = serializer.validated_data['action']
        if action == 'check_in' and (unit.status != 'vacant' or tenant.status != 'pending'):
            return Response({'action': ['Only a pending tenancy in a vacant unit can be checked in.']}, status=status.HTTP_400_BAD_REQUEST)
        if action == 'check_out' and (unit.status != 'occupied' or tenant.status not in ('active', 'expiring')):
            return Response({'action': ['Only an active or expiring tenancy in an occupied unit can be checked out.']}, status=status.HTTP_400_BAD_REQUEST)
        event = TenancyEvent.objects.create(
            tenant=tenant,
            unit=unit,
            action=action,
            recorded_by=request.user,
            notes=serializer.validated_data.get('notes', ''),
        )
        if action == 'check_in':
            unit.status = 'occupied'
            unit.tenant = tenant.name
            tenant.status = 'active'
        else:
            unit.status = 'vacant'
            unit.tenant = ''
            tenant.status = 'pending'
            if tenant.user_id:
                tenant.user.portal_access_granted = False
                tenant.user.save(update_fields=['portal_access_granted'])
        unit.save(update_fields=['status', 'tenant'])
        tenant.save(update_fields=['status'])
        property_record = Property.objects.select_for_update().get(pk=unit.property_id)
        property_record.total_units = Unit.objects.filter(property_id=unit.property_id).count()
        property_record.occupied_units = Unit.objects.filter(
            property_id=unit.property_id,
            status='occupied',
        ).count()
        property_record.save(update_fields=['total_units', 'occupied_units'])
    return Response(TenancyEventSerializer(event).data, status=status.HTTP_201_CREATED)


# Staff
@api_view(['GET', 'POST'])
@permission_classes([SmartNestAuthenticated])
def staff_list(request):
    if request.method == 'GET':
        if not has_role(request.user, 'manager'):
            return forbidden()
        staff = Staff.objects.all()
        serializer = StaffSerializer(staff, many=True)
        return Response(serializer.data)
    if not has_role(request.user, 'admin'):
        return forbidden()
    serializer = StaffSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([AllowAny])
def health(request):
    return Response({'status': 'ok', 'service': 'smartnest-api'})


# Expenses
@api_view(['GET', 'POST'])
@permission_classes([SmartNestAuthenticated])
def expenses_list(request):
    if request.method == 'GET':
        if request.user.role != 'manager':
            return forbidden()
        expenses = Expense.objects.all()
        serializer = ExpenseSerializer(expenses, many=True)
        return Response(serializer.data)
    if not has_role(request.user, 'manager'):
        return forbidden()
    serializer = ExpenseSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([SmartNestAuthenticated])
def expense_detail(request, pk):
    if request.user.role != 'manager':
        return forbidden()
    try:
        expenses = Expense.objects.all()
        expense = expenses.get(pk=pk)
    except Expense.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(ExpenseSerializer(expense).data)
    elif request.method == 'PUT':
        if not has_role(request.user, 'manager'):
            return forbidden()
        serializer = ExpenseSerializer(expense, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    elif request.method == 'DELETE':
        if not has_role(request.user, 'manager'):
            return forbidden()
        expense.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# Unit Inspections
@api_view(['GET', 'POST'])
@permission_classes([SmartNestAuthenticated])
def unit_inspections_list(request):
    if request.method == 'GET':
        if request.user.role not in ('manager', 'staff'):
            return forbidden()
        inspections = UnitInspection.objects.all()
        inspections = apply_staff_cluster(inspections, request.user, 'unit__property__cluster')
        serializer = UnitInspectionSerializer(inspections, many=True)
        return Response(serializer.data)
    if not has_role(request.user, 'manager', 'staff'):
        return forbidden()
    serializer = UnitInspectionSerializer(data=request.data)
    if serializer.is_valid():
        if request.user.role == 'staff':
            if not request.user.assigned_units.filter(pk=serializer.validated_data['unit'].id).exists():
                return forbidden()
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([SmartNestAuthenticated])
def unit_inspection_detail(request, pk):
    if request.user.role not in ('manager', 'staff'):
        return forbidden()
    try:
        inspections = UnitInspection.objects.all()
        inspections = apply_staff_cluster(inspections, request.user, 'unit__property__cluster')
        inspection = inspections.get(pk=pk)
    except UnitInspection.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(UnitInspectionSerializer(inspection).data)
    elif request.method == 'PUT':
        if not has_role(request.user, 'manager', 'staff'):
            return forbidden()
        serializer = UnitInspectionSerializer(inspection, data=request.data)
        if serializer.is_valid():
            if request.user.role == 'staff':
                unit = serializer.validated_data['unit']
                if not request.user.assigned_units.filter(pk=unit.id).exists():
                    return forbidden()
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    elif request.method == 'DELETE':
        if not has_role(request.user, 'manager'):
            return forbidden()
        inspection.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
