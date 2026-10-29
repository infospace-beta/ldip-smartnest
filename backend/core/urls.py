from django.urls import path
from . import views

urlpatterns = [
    path('health/', views.health, name='health'),

    # Auth
    path('auth/register/', views.register, name='register'),
    path('tenant-invitations/<str:token>/', views.tenant_invitation_details, name='tenant_invitation_details'),
    path('auth/login/', views.login, name='login'),
    path('auth/me/', views.me, name='me'),
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

    # Notices
    path('notices/', views.notices_list, name='notices_list'),
    path('notices/unread-count/', views.notices_unread_count, name='notices_unread_count'),

    # Maintenance
    path('maintenance/', views.maintenance_list, name='maintenance_list'),
    path('maintenance/<int:pk>/', views.maintenance_detail, name='maintenance_detail'),
    path('tenancy-events/', views.tenancy_events, name='tenancy_events'),
    path('tenancy-events/<int:pk>/photo/', views.tenancy_event_photo, name='tenancy_event_photo'),

    # Staff
    path('staff/', views.staff_list, name='staff_list'),

    # Expenses
    path('expenses/', views.expenses_list, name='expenses_list'),
    path('expenses/<int:pk>/', views.expense_detail, name='expense_detail'),

    # Unit Inspections
    path('unit-inspections/', views.unit_inspections_list, name='unit_inspections_list'),
    path('unit-inspections/<int:pk>/', views.unit_inspection_detail, name='unit_inspection_detail'),
]
