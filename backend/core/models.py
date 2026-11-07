from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid


class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('manager', 'Manager (Landlord)'),
        ('tenant', 'Tenant'),
        ('staff', 'Staff'),
        ('maintenance', 'Maintenance'),
    ]

    email = models.EmailField(unique=True)
    supabase_user_id = models.UUIDField(unique=True, null=True, blank=True, editable=False)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='tenant')
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.CharField(max_length=10, blank=True, default='U')
    avatar_image = models.FileField(upload_to='profile-photos/%Y/%m/', blank=True)
    property_cluster = models.CharField(max_length=100, blank=True)
    is_active_user = models.BooleanField(default=True)
    portal_access_granted = models.BooleanField(default=False)
    registration_consent_at = models.DateTimeField(null=True, blank=True)
    identity_verified_at = models.DateTimeField(null=True, blank=True, editable=False)
    onboarded_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='onboarded_team_members',
    )
    scope_to_assigned_units = models.BooleanField(default=False)
    assigned_units = models.ManyToManyField('Unit', related_name='assigned_users', blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'role']

    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return self.email


class Property(models.Model):
    owner = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='managed_properties',
    )
    name = models.CharField(max_length=200)
    location = models.CharField(max_length=200)
    cluster = models.CharField(max_length=100, default='Nairobi Cluster')
    total_units = models.PositiveIntegerField(default=0)
    occupied_units = models.PositiveIntegerField(default=0)
    monthly_rent = models.CharField(max_length=50, blank=True)
    tag = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, default='vacant')  # leased, vacant
    photo_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'properties'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class Unit(models.Model):
    STATUS_CHOICES = [
        ('occupied', 'Occupied'),
        ('vacant', 'Vacant'),
    ]

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='units')
    unit_number = models.CharField(max_length=50)
    unit_type = models.CharField(max_length=100)
    rent = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='vacant')
    tenant = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'units'
        ordering = ['unit_number']
        unique_together = ['property', 'unit_number']

    def __str__(self):
        return f'{self.unit_number} - {self.property.name}'


class Tenant(models.Model):
    move_out_at = models.DateTimeField(null=True,blank=True)
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expiring', 'Expiring Soon'),
        ('pending', 'Pending'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='tenancies')
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20)
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='tenants')
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='tenant_record', null=True, blank=True)
    lease_end = models.DateField()
    rent = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tenants'
        ordering = ['name']
        constraints = [models.UniqueConstraint(
            fields=['user'], condition=models.Q(status__in=['active', 'expiring']),
            name='one_active_tenancy_per_user',
        )]

    def __str__(self):
        return self.name


class TenantInvitation(models.Model):
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name='invitation')
    email = models.EmailField()
    token_digest = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='tenant_invitations')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'tenant_invitations'


class Payment(models.Model):
    METHOD_CHOICES = [
        ('mpesa', 'M-Pesa'),
        ('bank_transfer', 'Bank Transfer'),
        ('cash', 'Cash'),
    ]

    STATUS_CHOICES = [
        ('matched', 'Matched'),
        ('pending', 'Pending'),
        ('needs_review', 'Needs Review'),
    ]

    reference = models.CharField(max_length=50, unique=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='payments')
    date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    match_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'payments'
        ordering = ['-date']

    def __str__(self):
        return self.reference


class Notice(models.Model):
    sender = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='authored_notices')
    recipients = models.ManyToManyField(User, through='NoticeReceipt', related_name='directed_notices')
    important = models.BooleanField(default=False)
    encrypted_content = models.TextField(blank=True)
    link = models.CharField(max_length=200, blank=True)

    ICON_CHOICES = [
        ('receipt_long', 'receipt_long'),
        ('campaign', 'campaign'),
        ('schedule_send', 'schedule_send'),
        ('send', 'send'),
    ]

    STATE_CHOICES = [
        ('delivered', 'Delivered'),
        ('scheduled', 'Scheduled'),
        ('queued', 'Queued'),
    ]

    icon = models.CharField(max_length=50, choices=ICON_CHOICES, default='send')
    title = models.CharField(max_length=200)
    text = models.TextField()
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default='queued')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notices'
        ordering = ['-created_at']

    def save(self,*args,**kwargs):
        if self.title or self.text:
            from .workflow_crypto import seal
            self.encrypted_content=seal(self.title,self.text);self.title='';self.text=''
            if kwargs.get('update_fields'):
                kwargs['update_fields']=set(kwargs['update_fields'])|{'title','text','encrypted_content'}
        super().save(*args,**kwargs)

    def __str__(self):
        return 'Confidential notice'


class MaintenanceJob(models.Model):
    category = models.CharField(max_length=40, default='general')
    description = models.TextField(blank=True)
    requires_quotation = models.BooleanField(default=False)
    approved_budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    visit_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    reminder_at = models.DateTimeField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)
    completion_notes = models.TextField(blank=True)
    completion_photo = models.FileField(upload_to='maintenance-completion/%Y/%m/', blank=True)
    tenant_response = models.TextField(blank=True)
    conversation = models.OneToOneField('Conversation', null=True, blank=True, on_delete=models.SET_NULL, related_name='maintenance_job')

    PRIORITY_CHOICES = [
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]

    STATUS_CHOICES = [
        ('pending_approval', 'Pending approval'),
        ('awaiting_provider', 'Awaiting provider'),
        ('awaiting_confirmation', 'Awaiting tenant confirmation'),
        ('disputed', 'Disputed'),
        ('logged', 'Logged'),
        ('assigned', 'Assigned'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
    ]

    job_id = models.CharField(max_length=20, unique=True)
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='maintenance_jobs')
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='maintenance_jobs', null=True, blank=True)
    issue = models.CharField(max_length=200)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    reported_by = models.CharField(max_length=200)
    reported_by_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='maintenance_requests',
    )
    assignee = models.CharField(max_length=200)
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_maintenance_jobs',
    )
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='assigned')
    quote_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    quote_notes = models.TextField(blank=True)
    damage_photo = models.FileField(upload_to='maintenance/%Y/%m/', blank=True)
    confirmation_photo_url = models.URLField(blank=True)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_maintenance_jobs',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    manager_notes = models.TextField(blank=True)
    date = models.DateField()

    class Meta:
        db_table = 'maintenance_jobs'
        ordering = ['-date']

    def __str__(self):
        return self.job_id


class Staff(models.Model):
    name = models.CharField(max_length=200)
    initials = models.CharField(max_length=5)
    role = models.CharField(max_length=100)
    email = models.EmailField()
    roles = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = 'staff'

    def __str__(self):
        return self.name


class Expense(models.Model):
    CATEGORY_CHOICES = [
        ('repairs', 'Repairs'),
        ('utilities', 'Utilities'),
        ('maintenance', 'Maintenance'),
        ('insurance', 'Insurance'),
        ('taxes', 'Property Taxes'),
        ('management', 'Management Fees'),
        ('other', 'Other'),
    ]

    title = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='expenses', null=True, blank=True)
    description = models.TextField(blank=True)
    date = models.DateField()
    receipt_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'expenses'
        ordering = ['-date']

    def __str__(self):
        return self.title


class UnitInspection(models.Model):
    tenant = models.ForeignKey(Tenant, null=True, blank=True, on_delete=models.SET_NULL, related_name='inspections')
    inspector = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='inspections_to_perform')
    source_event = models.OneToOneField('TenancyEvent', null=True, blank=True, on_delete=models.SET_NULL, related_name='inspection')
    scheduled_at = models.DateTimeField(null=True, blank=True)
    requested_at = models.DateTimeField(null=True, blank=True)
    purpose = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=30, default='awaiting_confirmation')
    completed_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    agrees_with_report = models.BooleanField(null=True, blank=True)
    tenant_comments = models.TextField(blank=True)
    check_in = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='checkout_comparisons')
    maintenance = models.ForeignKey(MaintenanceJob, null=True, blank=True, on_delete=models.SET_NULL, related_name='source_inspections')
    proposed_charge = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    charge_reason = models.TextField(blank=True)
    charge_response = models.CharField(max_length=20, blank=True)
    charge_comments = models.TextField(blank=True)
    reminded_at = models.DateTimeField(null=True, blank=True)

    INSPECTION_TYPE_CHOICES = [
        ('routine', 'Routine'),
        ('move_in', 'Move-in'),
        ('move_out', 'Move-out'),
    ]

    CONDITION_CHOICES = [
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
    ]

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='inspections')
    inspection_type = models.CharField(max_length=20, choices=INSPECTION_TYPE_CHOICES, default='routine')
    inspector_name = models.CharField(max_length=200)
    inspection_date = models.DateField()
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='good')
    checklist = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    issues_found = models.TextField(blank=True)
    recommended_actions = models.TextField(blank=True)
    next_inspection_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'unit_inspections'
        ordering = ['-inspection_date']

    def __str__(self):
        return f'Inspection - {self.unit.unit_number} - {self.inspection_date}'


class TenancyEvent(models.Model):
    ACTION_CHOICES = [
        ('check_in', 'Check in'),
        ('check_out', 'Check out'),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='events')
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='tenancy_events')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    recorded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='recorded_tenancy_events')
    recorded_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    evidence_photo = models.FileField(upload_to='tenancy-events/%Y/%m/', blank=True)

    class Meta:
        db_table = 'tenancy_events'
        ordering = ['-recorded_at']


class Conversation(models.Model):
    subject = models.CharField(max_length=200)
    participants = models.ManyToManyField(User, related_name='conversations')
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_conversations')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'conversations'
        ordering = ['-created_at']


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.PROTECT, related_name='sent_messages')
    body = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'messages'
        ordering = ['sent_at']


class AccountInvitation(models.Model):
    property = models.ForeignKey(Property,null=True,blank=True,on_delete=models.PROTECT)
    unit = models.ForeignKey(Unit,null=True,blank=True,on_delete=models.PROTECT)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=[('manager', 'Manager'), ('staff', 'Staff'), ('maintenance', 'Maintenance')])
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='account_invitations')
    token_digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def issuer_valid(self):
        issuer = self.created_by
        scope_valid = not self.property_id or issuer.role == 'admin' or self.property.owner_id == issuer.pk
        scope_valid = scope_valid and (not self.unit_id or self.unit.property_id == self.property_id)
        return scope_valid and issuer.is_active and issuer.is_active_user and (
            (issuer.role == 'admin' and self.role == 'manager') or
            (issuer.role == 'manager' and self.role in ('staff', 'maintenance'))
        )


class NoticeReceipt(models.Model):
    notice = models.ForeignKey(Notice, on_delete=models.CASCADE, related_name='receipts')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    read_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['notice', 'user'], name='unique_notice_recipient')]


class WorkflowPolicy(models.Model):
    manager = models.OneToOneField(User, on_delete=models.CASCADE, related_name='workflow_policy')
    enabled = models.BooleanField(default=False)
    auto_approve = models.BooleanField(default=False)
    auto_reassign = models.BooleanField(default=True)
    reminders = models.BooleanField(default=True)
    inspections_enabled = models.BooleanField(default=True)
    spending_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    category_costs = models.JSONField(default=dict, blank=True)
    provider_categories = models.JSONField(default=dict, blank=True)
    provider_response_hours = models.PositiveIntegerField(default=24)
    job_due_hours = models.PositiveIntegerField(default=72)
    inspection_frequency_days = models.PositiveIntegerField(default=90)
    inspection_notice_hours = models.PositiveIntegerField(default=336)
    work_start_hour = models.PositiveIntegerField(default=9)
    work_end_hour = models.PositiveIntegerField(default=17)
    working_days = models.JSONField(default=list, blank=True)
    routine_sample_size = models.PositiveIntegerField(default=1)
    inspector = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='inspection_policies')
    last_routine_date = models.DateField(null=True, blank=True)
    worker_seen_at = models.DateTimeField(null=True, blank=True)


class MaintenanceOffer(models.Model):
    job = models.ForeignKey(MaintenanceJob, on_delete=models.CASCADE, related_name='offers')
    provider = models.ForeignKey(User, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, default='pending')
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['job', 'provider'], name='one_offer_per_provider')]


class InspectionPhoto(models.Model):
    inspection = models.ForeignKey(UnitInspection, on_delete=models.CASCADE, related_name='photos')
    image = models.FileField(upload_to='inspection-photos/%Y/%m/')
    caption = models.CharField(max_length=200, blank=True)
