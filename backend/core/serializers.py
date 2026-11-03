from decimal import Decimal
import hashlib
import secrets
from datetime import timedelta

from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from django.db import transaction
from .invitation_tokens import invitation_token, tenant_checked_in
from .models import (
    User, Property, Unit, Tenant, Payment, Notice, MaintenanceJob, Staff, Expense,
    UnitInspection, TenancyEvent, Conversation, Message, TenantInvitation,
)


def validate_image_upload(uploaded_file, label='Photos'):
    if uploaded_file.size > 5 * 1024 * 1024:
        raise serializers.ValidationError(f'{label} must be 5 MB or smaller.')
    signature = uploaded_file.read(12)
    uploaded_file.seek(0)
    is_image = (
        signature.startswith(b'\xff\xd8\xff')
        or signature.startswith(b'\x89PNG\r\n\x1a\n')
        or (signature.startswith(b'RIFF') and signature[8:12] == b'WEBP')
    )
    if not is_image:
        raise serializers.ValidationError(f'Upload a valid JPEG, PNG, or WebP image for {label.lower()}.')
    return uploaded_file


class UserSerializer(serializers.ModelSerializer):
    has_avatar = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'role', 'phone', 'avatar', 'has_avatar', 'property_cluster', 'is_active_user', 'portal_access_granted', 'date_joined', 'registration_consent_at']
        read_only_fields = ['id', 'date_joined', 'registration_consent_at']

    def get_has_avatar(self, obj):
        return bool(obj.avatar_image)


class UserProfileSerializer(serializers.ModelSerializer):
    remove_avatar = serializers.BooleanField(required=False, write_only=True)
    avatar_image = serializers.FileField(required=False, allow_empty_file=False)

    class Meta:
        model = User
        fields = ['email', 'username', 'phone', 'role', 'property_cluster', 'avatar', 'avatar_image', 'remove_avatar']
        read_only_fields = ['email', 'role', 'property_cluster', 'avatar']

    def validate(self, attrs):
        if attrs.get('remove_avatar') and attrs.get('avatar_image'):
            raise serializers.ValidationError('Choose a photo or remove it, not both.')
        return attrs

    def update(self, instance, validated_data):
        remove_avatar = validated_data.pop('remove_avatar', False)
        old_photo = instance.avatar_image if remove_avatar else None
        if remove_avatar:
            validated_data['avatar_image'] = ''
        instance = super().update(instance, validated_data)
        if old_photo:
            old_photo.delete(save=False)
        return instance

    def validate_avatar_image(self, uploaded_file):
        if uploaded_file.size > 5 * 1024 * 1024:
            raise serializers.ValidationError('Profile photos must be 5 MB or smaller.')
        signature = uploaded_file.read(12)
        uploaded_file.seek(0)
        if not (
            signature.startswith(b'\xff\xd8\xff')
            or signature.startswith(b'\x89PNG\r\n\x1a\n')
            or (signature.startswith(b'RIFF') and signature[8:12] == b'WEBP')
        ):
            raise serializers.ValidationError('Upload a valid JPEG, PNG, or WebP image.')
        return uploaded_file

    def validate_phone(self, value):
        if value and User.objects.filter(phone=value).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError('An account with this phone number already exists.')
        return value


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    consent = serializers.BooleanField(write_only=True, required=True)
    invitation_token = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ['email', 'username', 'password', 'role', 'phone', 'consent', 'invitation_token']

    def validate_role(self, value):
        if value != 'tenant':
            raise serializers.ValidationError('Public registration is limited to tenant accounts.')
        return value

    def validate_phone(self, value):
        if value and User.objects.filter(phone=value).exists():
            raise serializers.ValidationError('An account with this phone number already exists.')
        return value

    def validate_consent(self, value):
        if not value:
            raise serializers.ValidationError('Consent is required to create an account.')
        return value

    def validate_invitation_token(self, value):
        digest = hashlib.sha256(value.encode()).hexdigest()
        try:
            invitation = TenantInvitation.objects.select_for_update().select_related('tenant').get(
                token_digest=digest,
                accepted_at__isnull=True,
                expires_at__gt=timezone.now(),
            )
        except TenantInvitation.DoesNotExist as error:
            raise serializers.ValidationError('This tenant invitation is invalid or has expired.') from error
        if not tenant_checked_in(invitation.tenant):
            raise serializers.ValidationError('The manager must complete check-in before this invitation can be accepted.')
        if invitation.tenant.user_id:
            raise serializers.ValidationError('This tenant record already has an account.')
        if User.objects.filter(email__iexact=invitation.email).exists():
            raise serializers.ValidationError('An account already uses this email. Ask the manager to link that account instead.')
        self._invitation = invitation
        return value

    def validate(self, attrs):
        invitation = getattr(self, '_invitation', None)
        if invitation:
            if attrs['email'].casefold() != invitation.email.casefold():
                raise serializers.ValidationError({'email': 'Use the email address that received this invitation.'})
            if attrs['role'] != 'tenant':
                raise serializers.ValidationError({'role': 'Tenant invitations can only create tenant accounts.'})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password')
        validated_data.pop('consent')
        invitation_token = validated_data.pop('invitation_token', None)
        validated_data['registration_consent_at'] = timezone.now()
        invitation = getattr(self, '_invitation', None) if invitation_token else None
        validated_data['portal_access_granted'] = invitation is not None
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        if invitation:
            Tenant.objects.filter(pk=invitation.tenant_id, user__isnull=True).update(user=user)
            invitation.accepted_at = timezone.now()
            invitation.save(update_fields=['accepted_at'])
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        user = authenticate(username=email, password=password)
        if not user:
            raise serializers.ValidationError('Invalid email or password.')
        if not user.is_active or not user.is_active_user:
            raise serializers.ValidationError('Account is disabled.')
        if user.role == 'tenant' and (
            not user.portal_access_granted or not Tenant.objects.filter(user=user).exists()
        ):
            raise serializers.ValidationError('Your manager must link your tenant record before you can sign in.')
        attrs['user'] = user
        return attrs


class UserAccessSerializer(serializers.ModelSerializer):
    managed_properties = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Property.objects.all(), required=False, write_only=True,
    )
    managed_property_ids = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'role', 'property_cluster', 'is_active_user',
            'portal_access_granted', 'assigned_units',
            'managed_properties', 'managed_property_ids',
        ]
        read_only_fields = ['id', 'username', 'email', 'portal_access_granted']

    def validate_role(self, value):
        if (
            self.instance
            and self.instance.pk == self.context['request'].user.pk
            and value != self.instance.role
        ):
            raise serializers.ValidationError('You cannot change your own role.')
        return value

    def validate_is_active_user(self, value):
        if self.instance and self.instance.pk == self.context['request'].user.pk and not value:
            raise serializers.ValidationError('You cannot deactivate your own account.')
        return value

    def validate(self, attrs):
        role = attrs.get('role', getattr(self.instance, 'role', None))
        if role != 'staff' and attrs.get('assigned_units'):
            raise serializers.ValidationError({'assigned_units': 'Unit assignments are only available for staff.'})
        if role != 'manager' and attrs.get('managed_properties'):
            raise serializers.ValidationError({'managed_properties': 'Property ownership can only be assigned to managers.'})
        return attrs

    def get_managed_property_ids(self, obj):
        return list(obj.managed_properties.values_list('id', flat=True))

    def update(self, instance, validated_data):
        assigned_units = validated_data.pop('assigned_units', None)
        managed_properties = validated_data.pop('managed_properties', None)
        user = super().update(instance, validated_data)
        if assigned_units is not None:
            user.assigned_units.set(assigned_units)
        elif user.role != 'staff':
            user.assigned_units.clear()
        if managed_properties is not None:
            Property.objects.filter(owner=user).update(owner=None)
            Property.objects.filter(pk__in=[prop.pk for prop in managed_properties]).update(owner=user)
        elif user.role != 'manager':
            Property.objects.filter(owner=user).update(owner=None)
        return user


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = self.context['request'].user
        if not user.check_password(attrs['current_password']):
            raise serializers.ValidationError({'current_password': 'The current password is incorrect.'})
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'The passwords do not match.'})
        validate_password(attrs['new_password'], user)
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'The passwords do not match.'})
        user = self.context.get('reset_user')
        validate_password(attrs['new_password'], user)
        return attrs


class TeamMemberOnboardingSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=[('staff', 'Staff'), ('maintenance', 'Maintenance')])

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('An account with this username already exists.')
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return value

    def validate_phone(self, value):
        if value and User.objects.filter(phone=value).exists():
            raise serializers.ValidationError('An account with this phone number already exists.')
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User.objects.create_user(
            password=password,
            onboarded_by=self.context['request'].user,
            **validated_data,
        )
        return user


class TenantInvitationSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate(self, attrs):
        tenant = self.context['tenant']
        if not tenant_checked_in(tenant):
            raise serializers.ValidationError('Complete the tenant check-in before preparing an invitation.')
        if tenant.user_id:
            raise serializers.ValidationError('This tenant already has a linked account.')
        if User.objects.filter(email__iexact=attrs['email']).exists():
            raise serializers.ValidationError({'email': 'An account already uses this email. Link that account from Add a tenant instead.'})
        return attrs

    def create(self, validated_data):
        tenant = self.context['tenant']
        existing = TenantInvitation.objects.filter(tenant=tenant, accepted_at__isnull=True, expires_at__gt=timezone.now()).first()
        if existing:
            if existing.email.casefold() != validated_data['email'].casefold():
                raise serializers.ValidationError({'email': 'An active invitation already exists for a different email.'})
            token = invitation_token('tenant', tenant.pk, existing.expires_at)
            if existing.token_digest == hashlib.sha256(token.encode()).hexdigest():
                self.token = token
                return tenant
        expires_at = timezone.now() + timedelta(days=7)
        token = invitation_token('tenant', tenant.pk, expires_at)
        TenantInvitation.objects.update_or_create(
            tenant=tenant,
            defaults={
                'email': validated_data['email'],
                'token_digest': hashlib.sha256(token.encode()).hexdigest(),
                'created_by': self.context['request'].user,
                'expires_at': expires_at,
                'accepted_at': None,
            },
        )
        self.token = token
        return tenant


class PublicUserSerializer(serializers.ModelSerializer):
    has_avatar = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'role', 'phone', 'property_cluster', 'has_avatar']

    def get_has_avatar(self, obj):
        return bool(obj.avatar_image)


class CommunicationContactSerializer(serializers.ModelSerializer):
    has_avatar = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'role', 'has_avatar']

    def get_has_avatar(self, obj):
        return bool(obj.avatar_image)


class ConversationSerializer(serializers.ModelSerializer):
    participants = CommunicationContactSerializer(many=True, read_only=True)
    last_message_preview = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ['id', 'subject', 'participants', 'created_at', 'last_message_preview']

    def get_last_message_preview(self, obj):
        message = obj.messages.order_by('-sent_at').first()
        return message.body[:120] if message else ''


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.username', read_only=True)

    class Meta:
        model = Message
        fields = ['id', 'sender', 'sender_name', 'body', 'sent_at']
        read_only_fields = ['id', 'sender', 'sender_name', 'sent_at']


class TenancyEventSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    unit_number = serializers.CharField(source='unit.unit_number', read_only=True)
    property_name = serializers.CharField(source='unit.property.name', read_only=True)
    recorded_by_name = serializers.CharField(source='recorded_by.username', read_only=True)
    tenant_user_id = serializers.SerializerMethodField()
    tenant_has_avatar = serializers.SerializerMethodField()
    evidence_photo = serializers.SerializerMethodField()
    evidence_upload = serializers.FileField(write_only=True, required=False, allow_empty_file=False)

    class Meta:
        model = TenancyEvent
        fields = [
            'id', 'tenant', 'tenant_name', 'tenant_user_id', 'tenant_has_avatar',
            'unit', 'unit_number', 'property_name',
            'action', 'recorded_by', 'recorded_by_name', 'recorded_at', 'notes',
            'evidence_photo', 'evidence_upload',
        ]
        read_only_fields = ['id', 'recorded_by', 'recorded_by_name', 'recorded_at']

    def get_tenant_user_id(self, obj):
        return obj.tenant.user_id

    def get_tenant_has_avatar(self, obj):
        return bool(obj.tenant.user_id and obj.tenant.user.avatar_image)

    def get_evidence_photo(self, obj):
        return bool(obj.evidence_photo)

    def validate_evidence_upload(self, uploaded_file):
        if uploaded_file.size > 5 * 1024 * 1024:
            raise serializers.ValidationError('Photos must be 5 MB or smaller.')
        signature = uploaded_file.read(12)
        uploaded_file.seek(0)
        is_image = (
            signature.startswith(b'\xff\xd8\xff')
            or signature.startswith(b'\x89PNG\r\n\x1a\n')
            or (signature.startswith(b'RIFF') and signature[8:12] == b'WEBP')
        )
        if not is_image:
            raise serializers.ValidationError('Upload a valid JPEG, PNG, or WebP image.')
        return uploaded_file

    def validate(self, attrs):
        tenant = attrs['tenant']
        unit = attrs['unit']
        action = attrs['action']
        if tenant.unit_id != unit.id or tenant.property_id != unit.property_id:
            raise serializers.ValidationError({'unit': 'Choose the tenant’s assigned unit.'})
        if action == 'check_in' and (unit.status != 'vacant' or tenant.status != 'pending'):
            raise serializers.ValidationError({'action': 'Only a pending tenancy in a vacant unit can be checked in.'})
        if action == 'check_out' and (unit.status != 'occupied' or tenant.status not in ('active', 'expiring')):
            raise serializers.ValidationError({'action': 'Only an active or expiring tenancy in an occupied unit can be checked out.'})
        return attrs


class StartConversationSerializer(serializers.Serializer):
    recipient = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    subject = serializers.CharField(max_length=200)
    body = serializers.CharField()

    def validate_body(self, value):
        if not value.strip():
            raise serializers.ValidationError('Message cannot be empty.')
        return value.strip()


class CreateMessageSerializer(serializers.Serializer):
    body = serializers.CharField()

    def validate_body(self, value):
        if not value.strip():
            raise serializers.ValidationError('Message cannot be empty.')
        return value.strip()


class PropertySerializer(serializers.ModelSerializer):
    total_units = serializers.IntegerField(min_value=1, max_value=1000)
    occupancy_rate = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = ['id', 'name', 'location', 'cluster', 'total_units', 'occupied_units', 'monthly_rent', 'tag', 'status', 'occupancy_rate', 'photo_url', 'created_at']

    def create(self, validated_data):
        validated_data['occupied_units'] = 0
        validated_data['status'] = 'vacant'
        with transaction.atomic():
            prop = super().create(validated_data)
            Unit.objects.bulk_create([
                Unit(property=prop, unit_number=str(number), unit_type=prop.tag or 'House', rent=prop.monthly_rent or '0')
                for number in range(1, prop.total_units + 1)
            ])
        return prop

    def get_occupancy_rate(self, obj):
        if obj.total_units == 0:
            return 0
        return round((obj.occupied_units / obj.total_units) * 100, 1)


class TenantPropertySerializer(serializers.ModelSerializer):
    class Meta:
        model = Property
        fields = ['id', 'name', 'location']


class StaffPropertySerializer(serializers.ModelSerializer):
    total_units = serializers.SerializerMethodField()
    occupied_units = serializers.SerializerMethodField()
    occupancy_rate = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = ['id', 'name', 'location', 'total_units', 'occupied_units', 'status', 'occupancy_rate']

    def get_assigned_units(self, obj):
        return obj.units.filter(assigned_users=self.context['request'].user)

    def get_total_units(self, obj):
        return self.get_assigned_units(obj).count()

    def get_occupied_units(self, obj):
        return self.get_assigned_units(obj).filter(status='occupied').count()

    def get_occupancy_rate(self, obj):
        total = self.get_total_units(obj)
        return round((self.get_occupied_units(obj) / total) * 100, 1) if total else 0


class UnitSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source='property.name', read_only=True)

    class Meta:
        model = Unit
        fields = ['id', 'property', 'property_name', 'unit_number', 'unit_type', 'rent', 'status', 'tenant', 'created_at']


class TenantSerializer(serializers.ModelSerializer):
    can_invite = serializers.SerializerMethodField()
    property_name = serializers.CharField(source='property.name', read_only=True)
    unit_number = serializers.CharField(source='unit.unit_number', read_only=True)
    account_email = serializers.EmailField(write_only=True, required=False, allow_blank=True)
    account_linked = serializers.SerializerMethodField()
    account_user_id = serializers.IntegerField(source='user_id', read_only=True, allow_null=True)
    account_has_avatar = serializers.SerializerMethodField()
    invitation_email = serializers.SerializerMethodField()
    invitation_expires_at = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = ['id', 'name', 'phone', 'property', 'property_name', 'unit', 'unit_number', 'lease_end', 'rent', 'status', 'created_at', 'account_email', 'account_linked', 'account_user_id', 'account_has_avatar', 'invitation_email', 'invitation_expires_at', 'can_invite']

    def get_can_invite(self, obj):
        return not obj.user_id and tenant_checked_in(obj)

    def get_account_linked(self, obj):
        return obj.user_id is not None

    def get_account_has_avatar(self, obj):
        return bool(obj.user_id and obj.user.avatar_image)

    def _active_invitation(self, obj):
        invitation = getattr(obj, 'invitation', None)
        if invitation and invitation.accepted_at is None and invitation.expires_at > timezone.now():
            return invitation
        return None

    def get_invitation_email(self, obj):
        invitation = getattr(obj, 'invitation', None)
        return invitation.email if invitation else ''

    def get_invitation_expires_at(self, obj):
        invitation = self._active_invitation(obj)
        return invitation.expires_at if invitation else None

    def validate_account_email(self, value):
        if not value:
            return None
        account = User.objects.filter(email__iexact=value, role='tenant').first()
        if not account:
            raise serializers.ValidationError('No tenant account exists with this email address.')
        linked_records = Tenant.objects.filter(user=account)
        if self.instance:
            linked_records = linked_records.exclude(pk=self.instance.pk)
        if linked_records.exists():
            raise serializers.ValidationError('This account is already linked to a tenant record.')
        return account

    def validate(self, attrs):
        property_value = attrs.get('property', getattr(self.instance, 'property', None))
        unit_value = attrs.get('unit', getattr(self.instance, 'unit', None))
        if unit_value and property_value and unit_value.property_id != property_value.id:
            raise serializers.ValidationError({'unit': 'Choose a unit belonging to the selected property.'})
        return attrs

    def create(self, validated_data):
        account = validated_data.pop('account_email', None)
        if account:
            validated_data['user'] = account
        tenant = super().create(validated_data)
        if account:
            account.portal_access_granted = True
            account.save(update_fields=['portal_access_granted'])
        return tenant

    def update(self, instance, validated_data):
        account = validated_data.pop('account_email', None)
        if account:
            validated_data['user'] = account
        tenant = super().update(instance, validated_data)
        if account:
            account.portal_access_granted = True
            account.save(update_fields=['portal_access_granted'])
        return tenant


class PaymentSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)

    class Meta:
        model = Payment
        fields = ['id', 'reference', 'tenant', 'tenant_name', 'date', 'amount', 'method', 'match_status', 'created_at']


class NoticeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notice
        fields = ['id', 'icon', 'title', 'text', 'state', 'created_at']


class MaintenanceJobSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source='property.name', read_only=True)
    unit_number = serializers.CharField(source='unit.unit_number', read_only=True)
    reported_by_user_id = serializers.SerializerMethodField()
    reported_by_has_avatar = serializers.SerializerMethodField()
    assigned_to_name = serializers.CharField(source='assigned_to.username', read_only=True, default=None)
    assigned_to_has_avatar = serializers.SerializerMethodField()
    approved_by_name = serializers.CharField(source='approved_by.username', read_only=True, default=None)
    has_damage_photo = serializers.SerializerMethodField()
    damage_photo_upload = serializers.FileField(write_only=True, required=False, allow_empty_file=False)

    class Meta:
        model = MaintenanceJob
        fields = [
            'id', 'job_id', 'property', 'property_name', 'unit', 'unit_number', 'issue',
            'priority', 'reported_by', 'reported_by_user_id', 'reported_by_has_avatar',
            'assignee', 'assigned_to', 'assigned_to_name', 'assigned_to_has_avatar',
            'status', 'quote_amount', 'quote_notes', 'has_damage_photo', 'damage_photo_upload',
            'confirmation_photo_url', 'approved_by', 'approved_by_name', 'approved_at',
            'manager_notes', 'date',
        ]

    def get_reported_by_user_id(self, obj):
        return obj.reported_by_user_id

    def get_reported_by_has_avatar(self, obj):
        return bool(obj.reported_by_user and obj.reported_by_user.avatar_image)

    def get_assigned_to_has_avatar(self, obj):
        return bool(obj.assigned_to and obj.assigned_to.avatar_image)

    def get_has_damage_photo(self, obj):
        return bool(obj.damage_photo)

    def validate_damage_photo_upload(self, uploaded_file):
        return validate_image_upload(uploaded_file, 'Damage photos')

    def validate(self, attrs):
        property_value = attrs.get('property', getattr(self.instance, 'property', None))
        unit_value = attrs.get('unit', getattr(self.instance, 'unit', None))
        if unit_value and property_value and unit_value.property_id != property_value.id:
            raise serializers.ValidationError({'unit': 'Choose a unit belonging to the selected property.'})
        return attrs

    def create(self, validated_data):
        photo = validated_data.pop('damage_photo_upload', None)
        job = super().create(validated_data)
        if photo:
            job.damage_photo = photo
            job.save(update_fields=['damage_photo'])
        return job


class TenantMaintenanceRequestSerializer(serializers.Serializer):
    issue = serializers.CharField(max_length=200)
    priority = serializers.ChoiceField(choices=MaintenanceJob.PRIORITY_CHOICES, default='medium')
    damage_photo_upload = serializers.FileField(required=False, allow_empty_file=False, write_only=True)

    def validate_damage_photo_upload(self, uploaded_file):
        return validate_image_upload(uploaded_file, 'Damage photos')


class MaintenanceApprovalSerializer(serializers.Serializer):
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role='maintenance', is_active=True, is_active_user=True),
        required=False,
        allow_null=True,
    )
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class MaintenanceRejectionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class MaintenanceVendorUpdateSerializer(serializers.ModelSerializer):
    quote_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'), required=False, allow_null=True)

    class Meta:
        model = MaintenanceJob
        fields = ['status', 'quote_amount', 'quote_notes', 'confirmation_photo_url']
        extra_kwargs = {
            'status': {'required': False},
            'quote_notes': {'required': False},
            'confirmation_photo_url': {'required': False},
        }

    def validate_confirmation_photo_url(self, value):
        if value and not value.lower().startswith('https://'):
            raise serializers.ValidationError('Use a secure HTTPS photo URL.')
        return value

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError('Submit a status update, quote, or completion photo.')
        next_status = attrs.get('status')
        current_status = self.instance.status
        transitions = {
            'assigned': {'in_progress'},
            'logged': {'in_progress'},
            'in_progress': {'completed'},
        }
        if next_status and next_status not in transitions.get(current_status, set()):
            raise serializers.ValidationError({'status': 'Work orders move from logged to in progress, then completed.'})
        if (
            next_status == 'completed'
            and not attrs.get('confirmation_photo_url', self.instance.confirmation_photo_url)
        ):
            raise serializers.ValidationError({'confirmation_photo_url': 'Add a completion photo URL before marking this work order complete.'})
        return attrs


class StaffSerializer(serializers.ModelSerializer):
    class Meta:
        model = Staff
        fields = ['id', 'name', 'initials', 'role', 'email', 'roles']


class DashboardStatsSerializer(serializers.Serializer):
    total_properties = serializers.IntegerField()
    total_tenants = serializers.IntegerField()
    rental_income = serializers.CharField()
    expenses = serializers.CharField()
    occupied_units = serializers.IntegerField()
    vacant_units = serializers.IntegerField()
    active_leases = serializers.IntegerField()


class ExpenseSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source='property.name', read_only=True)

    class Meta:
        model = Expense
        fields = ['id', 'title', 'category', 'amount', 'property', 'property_name', 'description', 'date', 'receipt_url', 'created_at']


class UnitInspectionSerializer(serializers.ModelSerializer):
    unit_number = serializers.CharField(source='unit.unit_number', read_only=True)
    property_name = serializers.CharField(source='unit.property.name', read_only=True)

    class Meta:
        model = UnitInspection
        fields = ['id', 'unit', 'unit_number', 'property_name', 'inspection_type', 'inspector_name', 'inspection_date', 'condition', 'checklist', 'notes', 'issues_found', 'recommended_actions', 'next_inspection_date', 'created_at']
