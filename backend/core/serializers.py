from decimal import Decimal
import hashlib
import secrets
from datetime import timedelta

from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from .models import (
    User, Property, Unit, Tenant, Payment, Notice, MaintenanceJob, Staff, Expense,
    UnitInspection, TenancyEvent, Conversation, Message, TenantInvitation,
)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'role', 'phone', 'avatar', 'property_cluster', 'is_active_user', 'portal_access_granted', 'date_joined', 'registration_consent_at']
        read_only_fields = ['id', 'date_joined', 'registration_consent_at']


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email', 'username', 'phone', 'role', 'property_cluster', 'avatar']
        read_only_fields = ['email', 'role', 'property_cluster', 'avatar']

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
    assigned_units = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Unit.objects.all(), required=False,
    )
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
    assigned_units = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Unit.objects.all(), required=False,
    )

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

    def validate_assigned_units(self, value):
        manager = self.context['request'].user
        if any(unit.property.owner_id != manager.id for unit in value):
            raise serializers.ValidationError('Only units in properties you manage can be assigned.')
        return value

    def validate(self, attrs):
        if attrs['role'] == 'staff' and not attrs.get('assigned_units'):
            raise serializers.ValidationError({'assigned_units': 'Assign at least one unit to this staff account.'})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password')
        assigned_units = validated_data.pop('assigned_units', [])
        user = User.objects.create_user(password=password, **validated_data)
        user.assigned_units.set(assigned_units)
        return user


class TenantInvitationSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate(self, attrs):
        tenant = self.context['tenant']
        if tenant.user_id:
            raise serializers.ValidationError('This tenant already has a linked account.')
        if User.objects.filter(email__iexact=attrs['email']).exists():
            raise serializers.ValidationError({'email': 'An account already uses this email. Link that account from Add a tenant instead.'})
        return attrs

    def create(self, validated_data):
        tenant = self.context['tenant']
        token = secrets.token_urlsafe(32)
        TenantInvitation.objects.update_or_create(
            tenant=tenant,
            defaults={
                'email': validated_data['email'],
                'token_digest': hashlib.sha256(token.encode()).hexdigest(),
                'created_by': self.context['request'].user,
                'expires_at': timezone.now() + timedelta(days=7),
                'accepted_at': None,
            },
        )
        self.token = token
        return tenant


class CommunicationContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'role']


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
    evidence_photo = serializers.SerializerMethodField()
    evidence_upload = serializers.FileField(write_only=True, required=False, allow_empty_file=False)

    class Meta:
        model = TenancyEvent
        fields = [
            'id', 'tenant', 'tenant_name', 'unit', 'unit_number', 'property_name',
            'action', 'recorded_by', 'recorded_by_name', 'recorded_at', 'notes',
            'evidence_photo', 'evidence_upload',
        ]
        read_only_fields = ['id', 'recorded_by', 'recorded_by_name', 'recorded_at']

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
    occupancy_rate = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = ['id', 'name', 'location', 'cluster', 'total_units', 'occupied_units', 'monthly_rent', 'tag', 'status', 'occupancy_rate', 'photo_url', 'created_at']

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
    property_name = serializers.CharField(source='property.name', read_only=True)
    unit_number = serializers.CharField(source='unit.unit_number', read_only=True)
    account_email = serializers.EmailField(write_only=True, required=False, allow_blank=True)
    account_linked = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = ['id', 'name', 'phone', 'property', 'property_name', 'unit', 'unit_number', 'lease_end', 'rent', 'status', 'created_at', 'account_email', 'account_linked']

    def get_account_linked(self, obj):
        return obj.user_id is not None

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

    class Meta:
        model = MaintenanceJob
        fields = [
            'id', 'job_id', 'property', 'property_name', 'unit', 'unit_number', 'issue',
            'priority', 'reported_by', 'assignee', 'status', 'quote_amount', 'quote_notes',
            'confirmation_photo_url', 'date',
        ]

    def validate(self, attrs):
        property_value = attrs.get('property', getattr(self.instance, 'property', None))
        unit_value = attrs.get('unit', getattr(self.instance, 'unit', None))
        if unit_value and property_value and unit_value.property_id != property_value.id:
            raise serializers.ValidationError({'unit': 'Choose a unit belonging to the selected property.'})
        return attrs


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
