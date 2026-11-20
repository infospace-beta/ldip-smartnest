import hashlib
import mimetypes
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.decorators import throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.core.mail import send_mail
from django.http import FileResponse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
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
    PublicUserSerializer,
    PasswordChangeSerializer, PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    MaintenanceVendorUpdateSerializer,
    TenantMaintenanceRequestSerializer,
    MaintenanceApprovalSerializer,
    MaintenanceRejectionSerializer,
)

User = get_user_model()


class PasswordResetThrottle(AnonRateThrottle):
    scope = 'password_reset'


class SmartNestAuthenticated(IsAuthenticated):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if not request.user.is_active_user:
            raise AuthenticationFailed('This account has been disabled.')
        if settings.SUPABASE_AUTH_ENABLED and request.user.mfa_enabled:
            from .workflow_auth import requires_mfa
            from rest_framework.exceptions import PermissionDenied
            if requires_mfa(request):
                raise PermissionDenied('Authenticator verification is required. Open Account security to continue.')
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
    return Tenant.objects.filter(user=user, status__in=['active', 'expiring']).order_by('-created_at', '-pk').first()


def manager_scope(queryset, user):
    if user.role != 'manager':
        return queryset
    lookups = {
        Property: 'owner',
        Unit: 'property__owner',
        Tenant: 'property__owner',
        Payment: 'tenant__property__owner',
        MaintenanceJob: 'property__owner',
        Expense: 'property__owner',
        UnitInspection: 'unit__property__owner',
        TenancyEvent: 'unit__property__owner',
    }
    lookup = lookups.get(queryset.model)
    return queryset.filter(**{lookup: user}) if lookup else queryset.none()


def apply_staff_cluster(queryset, user, lookup):
    if user.role != 'staff':
        return queryset
    unit_ids = staff_unit_ids(user)
    if not unit_ids:
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


def staff_unit_ids(user):
    """Units a staff member can work with.

    Staff inherit the portfolio of the manager who onboarded them, while any
    explicit unit assignments made by an administrator are also respected.
    """
    if user.role != 'staff':
        return set()
    unit_ids = set(user.assigned_units.values_list('id', flat=True))
    if user.scope_to_assigned_units:
        return unit_ids
    manager = user.onboarded_by
    if manager and manager.role == 'manager':
        unit_ids.update(
            Unit.objects.filter(property__owner_id=manager.pk).values_list('id', flat=True)
        )
    return unit_ids


def maintenance_jobs_for(user):
    """Only an explicit account assignment grants provider access."""
    return MaintenanceJob.objects.filter(assigned_to=user)


def manager_for_staff(user):
    if user.role == 'staff' and user.onboarded_by and user.onboarded_by.role == 'manager':
        return user.onboarded_by
    return None


def assignable_maintenance_users(user):
    """Maintenance accounts a manager (or their staff) may assign work to."""
    users = User.objects.filter(
        role='maintenance',
        is_active=True,
        is_active_user=True,
    )
    if user.role == 'admin':
        return users
    manager = user if user.role == 'manager' else manager_for_staff(user)
    if not manager:
        return users.none()
    return users.filter(
        Q(onboarded_by=manager)
        | Q(assigned_maintenance_jobs__property__owner=manager)
    ).distinct()


def maintenance_scope(queryset, user):
    if user.role == 'manager':
        return manager_scope(queryset, user)
    if user.role == 'staff':
        unit_ids = staff_unit_ids(user)
        return queryset.filter(unit_id__in=unit_ids) if unit_ids else queryset.none()
    if user.role == 'maintenance':
        return queryset.filter(assigned_to=user)
    if user.role == 'tenant':
        return queryset.filter(reported_by_user=user)
    return queryset.none()


def can_contact(sender, recipient):
    if sender.pk == recipient.pk or not recipient.is_active or not recipient.is_active_user:
        return False
    if sender.role == 'admin':
        return True
    if recipient.role == 'admin':
        # Every active workspace role can request administrator support.
        return sender.role in ('manager', 'tenant', 'staff', 'maintenance')
    if sender.role == 'manager':
        return (
            recipient.role != 'admin'
            and (
                Tenant.objects.filter(user=recipient, property__owner=sender).exists()
                or recipient.assigned_units.filter(property__owner=sender).exists()
                or recipient.onboarded_by_id == sender.id
                or MaintenanceJob.objects.filter(
                    assigned_to=recipient,
                    property__owner=sender,
                ).exists()
            )
        )
    if sender.role == 'tenant':
        tenant = tenant_record(sender)
        if not tenant or not tenant.unit_id:
            return False
        if recipient.role == 'manager':
            return tenant.property.owner_id == recipient.id
        if recipient.role == 'staff':
            return tenant.unit_id in staff_unit_ids(recipient)
        if recipient.role == 'maintenance':
            return MaintenanceJob.objects.filter(
                reported_by_user=sender,
                status__in=('assigned', 'in_progress', 'awaiting_confirmation', 'disputed', 'completed'),
            ).filter(
                assigned_to=recipient,
            ).exists()
        return False
    if sender.role == 'staff':
        unit_ids = staff_unit_ids(sender)
        if recipient.role == 'manager':
            return (
                sender.onboarded_by_id == recipient.id
                or Property.objects.filter(owner=recipient, units__id__in=unit_ids).exists()
                or sender.assigned_units.filter(property__owner=recipient).exists()
            )
        if recipient.role == 'tenant':
            return Tenant.objects.filter(user=recipient, unit_id__in=unit_ids).exists()
        if recipient.role == 'maintenance':
            return MaintenanceJob.objects.filter(
                unit_id__in=unit_ids,
            ).filter(
                assigned_to=recipient,
            ).exists()
        return False
    if sender.role == 'maintenance':
        jobs = maintenance_jobs_for(sender)
        if recipient.role == 'manager':
            return jobs.filter(property__owner=recipient).exists()
        if recipient.role == 'staff':
            return jobs.filter(unit_id__in=staff_unit_ids(recipient)).exists()
        if recipient.role == 'tenant':
            return jobs.filter(reported_by_user=recipient).exists()
    return False


def can_view_user(viewer, target):
    return (
        viewer.pk == target.pk
        or viewer.role == 'admin'
        or can_contact(viewer, target)
        or can_contact(target, viewer)
    )


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
@transaction.atomic
def create_tenant_invitation(request, pk):
    if request.user.role not in ('manager', 'staff'):
        return forbidden()
    tenants = Tenant.objects.select_for_update(of=('self',)).select_related('property', 'unit')
    if request.user.role == 'manager':
        tenants = tenants.filter(property__owner=request.user)
    else:
        tenants = tenants.filter(unit_id__in=staff_unit_ids(request.user))
    tenant = tenants.filter(pk=pk).first()
    if not tenant:
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
@permission_classes([SmartNestAuthenticated])
def user_public_profile(request, pk):
    try:
        target = User.objects.get(pk=pk, is_active=True, is_active_user=True)
    except User.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    if not can_view_user(request.user, target):
        return forbidden()
    return Response(PublicUserSerializer(target).data)


@api_view(['GET'])
@permission_classes([SmartNestAuthenticated])
def user_avatar(request, pk):
    try:
        target = User.objects.get(pk=pk, is_active=True, is_active_user=True)
    except User.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    if not can_view_user(request.user, target):
        return forbidden()
    if not target.avatar_image:
        return Response({'error': 'No profile photo is available.'}, status=status.HTTP_404_NOT_FOUND)
    photo = target.avatar_image.open('rb')
    signature = photo.read(12)
    photo.seek(0)
    if signature.startswith(b'\xff\xd8\xff'):
        content_type = 'image/jpeg'
    elif signature.startswith(b'\x89PNG\r\n\x1a\n'):
        content_type = 'image/png'
    elif signature.startswith(b'RIFF') and signature[8:12] == b'WEBP':
        content_type = 'image/webp'
    else:
        photo.close()
        return Response({'error': 'The stored profile photo is invalid.'}, status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
    response = FileResponse(photo, content_type=content_type)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@api_view(['GET'])
@permission_classes([AllowAny])
def tenant_invitation_details(request, token):
    digest = hashlib.sha256(token.encode()).hexdigest()
    invitation = TenantInvitation.objects.select_related('tenant').filter(
        token_digest=digest,
        accepted_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).first()
    from .invitation_tokens import tenant_checked_in
    if not invitation or invitation.tenant.user_id or not tenant_checked_in(invitation.tenant):
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


class OwnProfileAuthenticated(SmartNestAuthenticated):
    def has_permission(self, request, view):
        # Confirmed tenants may read only their own profile while waiting for a
        # manager to link a tenancy. Operational endpoints remain protected.
        if request.method == 'GET':
            if not IsAuthenticated().has_permission(request, view):
                return False
            if not request.user.is_active or not request.user.is_active_user:
                raise AuthenticationFailed('This account has been disabled.')
            return True
        return super().has_permission(request, view)


@api_view(['GET', 'PATCH'])
@permission_classes([OwnProfileAuthenticated])
def me(request):
    if request.method == 'GET':
        return Response(UserSerializer(request.user,context={"request":request}).data)
    serializer = UserProfileSerializer(request.user, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(UserSerializer(serializer.instance,context={"request":request}).data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([PasswordResetThrottle])
def request_password_reset(request):
    serializer = PasswordResetRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user = User.objects.filter(
        email__iexact=serializer.validated_data['email'],
        is_active=True,
        is_active_user=True,
    ).first()
    if user:
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_url = (
            f"{settings.FRONTEND_URL.rstrip('/')}/reset-password"
            f"?uid={uid}&token={token}"
        )
        send_mail(
            'Reset your SmartNest password',
            f'Use this link to reset your SmartNest password. It expires after a short time:\n\n{reset_url}\n\n'
            'If you did not request this, you can ignore this email.',
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )

    return Response({
        'message': 'If an active account uses that email, a password reset link has been sent.',
    })


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([PasswordResetThrottle])
def confirm_password_reset(request):
    uid = request.data.get('uid', '')
    token = request.data.get('token', '')
    try:
        user_id = force_str(urlsafe_base64_decode(uid))
        user = User.objects.get(pk=user_id, is_active=True, is_active_user=True)
    except (TypeError, ValueError, OverflowError, UnicodeDecodeError, User.DoesNotExist):
        return Response({'error': 'This reset link is invalid or has expired.'}, status=status.HTTP_400_BAD_REQUEST)

    if not default_token_generator.check_token(user, token):
        return Response({'error': 'This reset link is invalid or has expired.'}, status=status.HTTP_400_BAD_REQUEST)

    serializer = PasswordResetConfirmSerializer(
        data=request.data,
        context={'reset_user': user},
    )
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    user.set_password(serializer.validated_data['new_password'])
    user.save(update_fields=['password'])
    return Response({'message': 'Your password has been updated. Sign in with your new password.'})


@api_view(['POST'])
@permission_classes([SmartNestAuthenticated])
def change_password(request):
    serializer = PasswordChangeSerializer(
        data=request.data,
        context={'request': request},
    )
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    request.user.set_password(serializer.validated_data['new_password'])
    request.user.save(update_fields=['password'])
    return Response({'message': 'Your password has been updated. Sign in again with your new password.'})


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
        'properties': [
            {'id': prop.id, 'name': prop.name, 'owner_id': prop.owner_id}
            for prop in Property.objects.order_by('name')
        ],
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
    return Response({'error':'Send an account invitation instead. Each person must choose their own password.'},status=405)


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

    properties = apply_staff_cluster(manager_scope(Property.objects.all(), user), user, 'cluster')
    tenants = apply_staff_cluster(manager_scope(Tenant.objects.all(), user), user, 'property__cluster')
    units = apply_staff_cluster(manager_scope(Unit.objects.all(), user), user, 'property__cluster')
    payments = apply_staff_cluster(manager_scope(Payment.objects.all(), user), user, 'tenant__property__cluster')
    expenses = manager_scope(Expense.objects.all(), user)
    total_properties = properties.count()
    total_tenants = tenants.count()
    total_income = 0
    total_expenses = 0
    if user.role == 'manager':
        total_income = payments.aggregate(total=Sum('amount'))['total'] or 0
        total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or 0
    occupied_units = units.filter(status='occupied').count()
    vacant_units = units.filter(status='vacant').count()
    active_leases = tenants.filter(status='active').count()

    data = {
        'total_properties': total_properties,
        'total_tenants': total_tenants,
        'rental_income': f'KSh {total_income:,.0f}' if user.role == 'manager' else '',
        'expenses': f'KSh {total_expenses:,.0f}' if user.role == 'manager' else '',
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
        properties = manager_scope(Property.objects.all(), request.user)
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
        serializer.save(owner=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([SmartNestAuthenticated])
def property_detail(request, pk):
    if request.user.role == 'admin' or request.user.role not in ('manager', 'staff', 'tenant'):
        return forbidden()
    try:
        properties = manager_scope(Property.objects.all(), request.user)
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
        units = manager_scope(Unit.objects.all(), request.user)
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
        if (
            request.user.role == 'manager'
            and serializer.validated_data['property'].owner_id != request.user.id
        ):
            return forbidden()
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
        tenants = manager_scope(
            Tenant.objects.select_related('property', 'unit', 'user', 'invitation'),
            request.user,
        )
        if request.user.role == 'tenant':
            tenants = tenants.filter(user=request.user)
        tenants = apply_staff_cluster(tenants, request.user, 'property__cluster')
        serializer = TenantSerializer(tenants, many=True)
        return Response(serializer.data)
    if not has_role(request.user, 'manager'):
        return forbidden()
    serializer = TenantSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        if serializer.validated_data['property'].owner_id != request.user.id:
            return forbidden()
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
        payments = manager_scope(Payment.objects.all(), request.user)
        if request.user.role == 'tenant':
            payments = payments.filter(tenant__user=request.user)
        serializer = PaymentSerializer(payments, many=True)
        return Response(serializer.data)
    if not has_role(request.user, 'manager'):
        return forbidden()
    serializer = PaymentSerializer(data=request.data)
    if serializer.is_valid():
        if serializer.validated_data['tenant'].property.owner_id != request.user.id:
            return forbidden()
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
        jobs = MaintenanceJob.objects.select_related(
            'property', 'unit', 'reported_by_user', 'assigned_to', 'approved_by',
        )
        jobs = maintenance_scope(jobs, request.user)
        serializer = MaintenanceJobSerializer(jobs, many=True)
        return Response(serializer.data)
    if request.user.role == 'tenant':
        tenant = tenant_record(request.user)
        if not tenant or not tenant.unit_id:
            return Response({'error': 'A linked tenant and unit record is required to submit a maintenance request.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = TenantMaintenanceRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        values = serializer.validated_data
        job = MaintenanceJob.objects.create(
            job_id=f'REQ-{uuid4().hex[:10].upper()}',
            property_id=tenant.property_id,
            unit_id=tenant.unit_id,
            issue=values['issue'].strip(),
            reported_by=tenant.name,
            reported_by_user=request.user,
            assignee='Property management',
            priority=values['priority'],
            status='pending_approval',
            date=timezone.localdate(),
        )
        photo = values.get('damage_photo_upload')
        if photo:
            job.damage_photo = photo
            job.save(update_fields=['damage_photo'])
        return Response(MaintenanceJobSerializer(job).data, status=status.HTTP_201_CREATED)
    if not has_role(request.user, 'manager', 'staff'):
        return forbidden()
    serializer = MaintenanceJobSerializer(data=request.data)
    if serializer.is_valid():
        if (
            request.user.role == 'manager'
            and serializer.validated_data['property'].owner_id != request.user.id
        ):
            return forbidden()
        if request.user.role == 'staff':
            unit = serializer.validated_data.get('unit')
            if not unit or unit.pk not in staff_unit_ids(request.user):
                return forbidden()
        assigned_to = serializer.validated_data.get('assigned_to')
        if assigned_to and not assignable_maintenance_users(request.user).filter(pk=assigned_to.pk).exists():
            return Response({'assigned_to': ['Choose a maintenance team member linked to this portfolio.']}, status=status.HTTP_400_BAD_REQUEST)
        job = serializer.save()
        return Response(MaintenanceJobSerializer(job).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([SmartNestAuthenticated])
def maintenance_assignees(request):
    if request.user.role not in ('admin', 'manager', 'staff'):
        return forbidden()
    users = assignable_maintenance_users(request.user).order_by('username')
    return Response(CommunicationContactSerializer(users, many=True).data)


@api_view(['GET', 'PATCH'])
@permission_classes([SmartNestAuthenticated])
def maintenance_detail(request, pk):
    if request.user.role not in ('manager', 'staff', 'maintenance', 'tenant'):
        return forbidden()
    jobs = MaintenanceJob.objects.select_related(
        'property', 'unit', 'reported_by_user', 'assigned_to', 'approved_by',
    )
    jobs = maintenance_scope(jobs, request.user)
    try:
        job = jobs.get(pk=pk)
    except MaintenanceJob.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(MaintenanceJobSerializer(job).data)
    if request.user.role == 'maintenance':
        if job.status not in ('assigned', 'in_progress'):
            return Response({'error': 'Only approved work orders can be updated.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = MaintenanceVendorUpdateSerializer(job, data=request.data, partial=True)
    elif request.user.role in ('manager', 'staff'):
        if job.status == 'pending_approval':
            return Response({'error': 'Use the approval action to process tenant requests.'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
        serializer = MaintenanceJobSerializer(job, data=request.data, partial=True)
    else:
        return forbidden()
    if serializer.is_valid():
        if (
            request.user.role == 'manager'
            and serializer.validated_data.get('property', job.property).owner_id != request.user.id
        ):
            return forbidden()
        if request.user.role == 'staff':
            unit = serializer.validated_data.get('unit', job.unit)
            if not unit or unit.pk not in staff_unit_ids(request.user):
                return forbidden()
        assigned_to = serializer.validated_data.get('assigned_to')
        if assigned_to and not assignable_maintenance_users(request.user).filter(pk=assigned_to.pk).exists():
            return Response({'assigned_to': ['Choose a maintenance team member linked to this portfolio.']}, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(MaintenanceJobSerializer(job).data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([SmartNestAuthenticated])
def maintenance_approve(request, pk):
    if request.user.role not in ('manager', 'staff'):
        return forbidden()
    jobs = MaintenanceJob.objects.select_related('property', 'unit')
    jobs = maintenance_scope(jobs, request.user)
    try:
        job = jobs.get(pk=pk)
    except MaintenanceJob.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    if job.status != 'pending_approval':
        return Response({'error': 'Only requests awaiting approval can be approved.'}, status=status.HTTP_400_BAD_REQUEST)
    serializer = MaintenanceApprovalSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    assigned_to = serializer.validated_data.get('assigned_to')
    if assigned_to and not assignable_maintenance_users(request.user).filter(pk=assigned_to.pk).exists():
        return Response({'assigned_to': ['Choose a maintenance team member linked to this portfolio.']}, status=status.HTTP_400_BAD_REQUEST)
    if not assigned_to:
        assigned_to = assignable_maintenance_users(request.user).order_by('id').first()
    job.status = 'assigned'
    job.approved_by = request.user
    job.approved_at = timezone.now()
    job.manager_notes = serializer.validated_data.get('note', '').strip()
    job.assigned_to = assigned_to
    job.assignee = assigned_to.username if assigned_to else 'Property management'
    job.save(update_fields=[
        'status', 'approved_by', 'approved_at', 'manager_notes', 'assigned_to', 'assignee',
    ])
    return Response(MaintenanceJobSerializer(job).data)


@api_view(['POST'])
@permission_classes([SmartNestAuthenticated])
def maintenance_reject(request, pk):
    if request.user.role not in ('manager', 'staff'):
        return forbidden()
    jobs = MaintenanceJob.objects.select_related('property', 'unit')
    jobs = maintenance_scope(jobs, request.user)
    try:
        job = jobs.get(pk=pk)
    except MaintenanceJob.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    if job.status != 'pending_approval':
        return Response({'error': 'Only requests awaiting approval can be declined.'}, status=status.HTTP_400_BAD_REQUEST)
    serializer = MaintenanceRejectionSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    job.status = 'rejected'
    job.approved_by = request.user
    job.approved_at = timezone.now()
    job.manager_notes = serializer.validated_data.get('reason', '').strip()
    job.save(update_fields=['status', 'approved_by', 'approved_at', 'manager_notes'])
    return Response(MaintenanceJobSerializer(job).data)


@api_view(['GET'])
@permission_classes([SmartNestAuthenticated])
def maintenance_photo(request, pk):
    if request.user.role not in ('manager', 'staff', 'maintenance', 'tenant'):
        return forbidden()
    jobs = MaintenanceJob.objects.all()
    jobs = maintenance_scope(jobs, request.user)
    try:
        job = jobs.get(pk=pk)
    except MaintenanceJob.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    if not job.damage_photo:
        return Response({'error': 'No damage photo is attached to this request.'}, status=status.HTTP_404_NOT_FOUND)
    photo = job.damage_photo.open('rb')
    signature = photo.read(12)
    photo.seek(0)
    if signature.startswith(b'\xff\xd8\xff'):
        content_type = 'image/jpeg'
    elif signature.startswith(b'\x89PNG\r\n\x1a\n'):
        content_type = 'image/png'
    elif signature.startswith(b'RIFF') and signature[8:12] == b'WEBP':
        content_type = 'image/webp'
    else:
        photo.close()
        return Response({'error': 'The stored damage photo is invalid.'}, status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
    response = FileResponse(photo, content_type=content_type)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@api_view(['GET', 'POST'])
@permission_classes([SmartNestAuthenticated])
def tenancy_events(request):
    if request.user.role not in ('manager', 'staff'):
        return forbidden()
    if request.method == 'GET':
        events = manager_scope(
            TenancyEvent.objects.select_related(
                'tenant', 'tenant__user', 'unit', 'unit__property', 'recorded_by',
            ),
            request.user,
        )
        if request.user.role == 'staff':
            events = events.filter(unit_id__in=staff_unit_ids(request.user))
        return Response(TenancyEventSerializer(events, many=True).data)

    serializer = TenancyEventSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    tenant = serializer.validated_data['tenant']
    unit = serializer.validated_data['unit']
    if unit.property.owner_id != request.user.id and request.user.role == 'manager':
        return forbidden()
    if request.user.role == 'staff' and unit.pk not in staff_unit_ids(request.user):
        return forbidden()

    with transaction.atomic():
        Property.objects.select_for_update().get(pk=unit.property_id)
        unit = Unit.objects.select_for_update().get(pk=unit.pk)
        tenant = Tenant.objects.select_for_update().get(pk=tenant.pk)
        if tenant.unit_id != unit.id or tenant.property_id != unit.property_id:
            return Response({'unit': ['Choose the tenant’s assigned unit.']}, status=status.HTTP_400_BAD_REQUEST)
        action = serializer.validated_data['action']
        if action == 'check_in' and (unit.status != 'vacant' or tenant.status != 'pending'):
            return Response({'action': ['Only a pending tenancy in a vacant unit can be checked in.']}, status=status.HTTP_400_BAD_REQUEST)
        if action == 'check_out' and (unit.status != 'occupied' or tenant.status not in ('active', 'expiring')):
            return Response({'action': ['Only an active or expiring tenancy in an occupied unit can be checked out.']}, status=status.HTTP_400_BAD_REQUEST)
        event_data = {
            'tenant': tenant,
            'unit': unit,
            'action': action,
            'recorded_by': request.user,
            'notes': serializer.validated_data.get('notes', ''),
        }
        if 'evidence_upload' in serializer.validated_data:
            event_data['evidence_photo'] = serializer.validated_data['evidence_upload']
        event = TenancyEvent.objects.create(**event_data)
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
        property_record.status = 'leased' if property_record.occupied_units else 'vacant'
        property_record.save(update_fields=['total_units', 'occupied_units', 'status'])
    return Response(TenancyEventSerializer(event).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([SmartNestAuthenticated])
def tenancy_event_photo(request, pk):
    if request.user.role not in ('manager', 'staff'):
        return forbidden()
    events = manager_scope(TenancyEvent.objects.all(), request.user)
    if request.user.role == 'staff':
        events = events.filter(unit_id__in=staff_unit_ids(request.user))
    try:
        event = events.get(pk=pk)
    except TenancyEvent.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    if not event.evidence_photo:
        return Response({'error': 'No photo is attached to this event.'}, status=status.HTTP_404_NOT_FOUND)
    content_type = mimetypes.guess_type(event.evidence_photo.name)[0] or 'application/octet-stream'
    response = FileResponse(event.evidence_photo.open('rb'), content_type=content_type)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


# Staff
@api_view(['GET', 'POST'])
@permission_classes([SmartNestAuthenticated])
def staff_list(request):
    if request.method == 'GET':
        if not has_role(request.user, 'admin'):
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
        expenses = manager_scope(Expense.objects.all(), request.user)
        serializer = ExpenseSerializer(expenses, many=True)
        return Response(serializer.data)
    if not has_role(request.user, 'manager'):
        return forbidden()
    serializer = ExpenseSerializer(data=request.data)
    if serializer.is_valid():
        property_record = serializer.validated_data.get('property')
        if not property_record:
            return Response({'property': ['Select one of your managed properties.']}, status=status.HTTP_400_BAD_REQUEST)
        if property_record.owner_id != request.user.id:
            return forbidden()
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([SmartNestAuthenticated])
def expense_detail(request, pk):
    if request.user.role != 'manager':
        return forbidden()
    try:
        expenses = manager_scope(Expense.objects.all(), request.user)
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
            property_record = serializer.validated_data.get('property', expense.property)
            if property_record.owner_id != request.user.id:
                return forbidden()
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
        inspections = manager_scope(UnitInspection.objects.all(), request.user)
        inspections = apply_staff_cluster(inspections, request.user, 'unit__property__cluster')
        serializer = UnitInspectionSerializer(inspections, many=True)
        return Response(serializer.data)
    if not has_role(request.user, 'manager', 'staff'):
        return forbidden()
    serializer = UnitInspectionSerializer(data=request.data)
    if serializer.is_valid():
        if (
            request.user.role == 'manager'
            and serializer.validated_data['unit'].property.owner_id != request.user.id
        ):
            return forbidden()
        if request.user.role == 'staff':
            if serializer.validated_data['unit'].pk not in staff_unit_ids(request.user):
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
        inspections = manager_scope(UnitInspection.objects.all(), request.user)
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
            if (
                request.user.role == 'manager'
                and serializer.validated_data.get('unit', inspection.unit).property.owner_id != request.user.id
            ):
                return forbidden()
            if request.user.role == 'staff':
                unit = serializer.validated_data['unit']
                if unit.pk not in staff_unit_ids(request.user):
                    return forbidden()
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    elif request.method == 'DELETE':
        if not has_role(request.user, 'manager'):
            return forbidden()
        inspection.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
