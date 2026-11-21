from django.conf import settings
from django.urls import path
from . import views
from . import onboarding_backend
from . import manager_team
from . import workflow_views as workflow
from .health import readiness
from .task_inbox import task_inbox
from . import daraja_views as daraja
from .account_security import security_settings
from .invitation_accept import accept_invitation

urlpatterns = [
    path('health/ready/', readiness, name='readiness'),
    path('invitation-property-options/', workflow.invitation_property_options),
    path('tenants/<int:pk>/move-out/', workflow.record_moveout),
    path('maintenance/<int:pk>/inspection-photos/<int:photo_pk>/', workflow.maintenance_inspection_photo),
    path('workflow-policy/', workflow.policy),
    path('notices/<int:pk>/read/', workflow.read_notice),
    path('maintenance/<int:pk>/actions/<str:action>/', workflow.maintenance_action),
    path('maintenance/<int:pk>/completion-photo/', workflow.completion_photo),
    path('unit-inspections/<int:pk>/actions/<str:action>/', workflow.inspection_detail),
    path('unit-inspections/<int:pk>/photos/<int:photo_pk>/', workflow.inspection_photo),

    path('health/', views.health, name='health'),
    path('team/', manager_team.manager_team, name='manager_team'),
    path('team/invitations/<uuid:pk>/link/', manager_team.manager_team_invitation_link, name='manager_team_invitation_link'),
    path('account-invitations/', onboarding_backend.account_invitations, name='account_invitations'),
    path('account-invitations/<str:token>/', onboarding_backend.account_invitation_details, name='account_invitation_details'),
    path('properties/<int:pk>/units/<int:unit_pk>/check-in/', onboarding_backend.check_in_unit, name='check_in_unit'),

    # Auth
    path('auth/register/', views.register, name='register'),
    path('tenant-invitations/<str:token>/', views.tenant_invitation_details, name='tenant_invitation_details'),
    path('auth/login/', views.login, name='login'),
    path('auth/me/', views.me, name='me'),
    path('auth/invitations/accept/', accept_invitation, name='accept_existing_invitation'),
    path('auth/security/', security_settings, name='account_security'),
    path('users/<int:pk>/avatar/', views.user_avatar, name='user_avatar'),
    path('users/<int:pk>/profile/', views.user_public_profile, name='user_public_profile'),
    path('auth/password/change/', views.change_password, name='change_password'),
    path('auth/password/reset/', views.request_password_reset, name='request_password_reset'),
    path('auth/password/reset/confirm/', views.confirm_password_reset, name='confirm_password_reset'),
    path('users/', views.user_access_list, name='user_access_list'),
    path('users/assignment-options/', views.user_assignment_options, name='user_assignment_options'),
    path('users/<int:pk>/', views.user_access_list, name='user_access_detail'),
    path('team/onboarding/', views.team_onboarding, name='team_onboarding'),
    path('communication/contacts/', views.communication_contacts, name='communication_contacts'),
    path('communication/conversations/', views.conversations_list, name='conversations_list'),
    path('communication/conversations/<int:pk>/messages/', views.conversation_messages, name='conversation_messages'),

    path('dashboard/tasks/', task_inbox, name='task_inbox'),

    # Dashboard
    path('dashboard/stats/', views.dashboard_stats, name='dashboard_stats'),

    # Properties
    path('properties/', views.properties_list, name='properties_list'),
    path('properties/<int:pk>/', views.property_detail, name='property_detail'),

    # Units
    path('units/', views.units_list, name='units_list'),

    # Tenants
    path('tenants/', views.tenants_list, name='tenants_list'),
    path('tenants/<int:pk>/invite/', views.create_tenant_invitation, name='create_tenant_invitation'),

    # Payments
    path('payments/', views.payments_list, name='payments_list'),
    path('payments/mpesa/', daraja.sandbox_payments, name='mpesa_sandbox'),
    path('payments/mpesa/<uuid:pk>/query/', daraja.sandbox_query, name='mpesa_sandbox_query'),
    path('payments/mpesa/callback/<uuid:pk>/<uuid:secret>/', daraja.sandbox_callback, name='mpesa_sandbox_callback'),

    # Notices
    path('notices/', workflow.notices, name='notices_list'),
    path('notices/unread-count/', workflow.unread, name='notices_unread_count'),

    # Maintenance
    path('maintenance/', workflow.maintenance, name='maintenance_list'),
    path('maintenance/assignees/', views.maintenance_assignees, name='maintenance_assignees'),
    path('maintenance/<int:pk>/', workflow.maintenance_detail, name='maintenance_detail'),
    path('maintenance/<int:pk>/approve/', workflow.maintenance_action, {'action':'approve'}, name='maintenance_approve'),
    path('maintenance/<int:pk>/reject/', workflow.maintenance_action, {'action':'reject'}, name='maintenance_reject'),
    path('maintenance/<int:pk>/photo/', views.maintenance_photo, name='maintenance_photo'),
    path('tenancy-events/', views.tenancy_events, name='tenancy_events'),
    path('tenancy-events/<int:pk>/photo/', views.tenancy_event_photo, name='tenancy_event_photo'),

    # Staff
    path('staff/', views.staff_list, name='staff_list'),

    # Expenses
    path('expenses/', views.expenses_list, name='expenses_list'),
    path('expenses/<int:pk>/', views.expense_detail, name='expense_detail'),

    # Unit Inspections
    path('unit-inspections/', workflow.inspections, name='unit_inspections_list'),
    path('unit-inspections/<int:pk>/', workflow.inspection_detail, name='unit_inspection_detail'),
]

if settings.SUPABASE_AUTH_ENABLED:
    legacy_auth_names = {'register', 'login', 'change_password', 'request_password_reset', 'confirm_password_reset'}
    urlpatterns = [pattern for pattern in urlpatterns if pattern.name not in legacy_auth_names]
