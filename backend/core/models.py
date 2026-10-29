from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('manager', 'Manager (Landlord)'),
        ('tenant', 'Tenant'),
        ('staff', 'Staff'),
        ('maintenance', 'Maintenance'),
    ]

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='tenant')
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.CharField(max_length=10, blank=True, default='U')
    avatar_image = models.FileField(upload_to='profile-photos/%Y/%m/', blank=True)
    property_cluster = models.CharField(max_length=100, blank=True)
    is_active_user = models.BooleanField(default=True)
    portal_access_granted = models.BooleanField(default=False)
    registration_consent_at = models.DateTimeField(null=True, blank=True)
    onboarded_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='onboarded_team_members',
    )
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
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expiring', 'Expiring Soon'),
        ('pending', 'Pending'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True, related_name='tenant_profile')
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

    def __str__(self):
        return self.title


class MaintenanceJob(models.Model):
    PRIORITY_CHOICES = [
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]

    STATUS_CHOICES = [
        ('logged', 'Logged'),
        ('assigned', 'Assigned'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
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
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='assigned')
    quote_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    quote_notes = models.TextField(blank=True)
    confirmation_photo_url = models.URLField(blank=True)
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
