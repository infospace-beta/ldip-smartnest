from datetime import timedelta
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from .models import MaintenanceJob, User
from .views import SmartNestAuthenticated, maintenance_scope
from .workflow_views import inspection_scope


@api_view(['GET'])
@permission_classes([SmartNestAuthenticated])
def task_inbox(request):
    now = timezone.now()
    tasks, counts = [], {}
    if request.user.role == 'admin':
        counts['pending_access'] = User.objects.filter(role='tenant', portal_access_granted=False, is_active=True, is_active_user=True).count()
        if counts['pending_access']:
            tasks.append({'id': 'access', 'title': 'Review tenant access', 'detail': 'Managers must link the tenancy before access is granted.', 'href': '/dashboard/staff', 'kind': 'access', 'due_at': None})
    else:
        jobs = maintenance_scope(MaintenanceJob.objects.select_related('property', 'unit'), request.user)
        groups = []
        if request.user.role == 'manager':
            groups.append(('approvals', jobs.filter(status__in=['pending_approval', 'logged']), 'Review repair request'))
        if request.user.role == 'tenant':
            groups.append(('confirmations', jobs.filter(status='awaiting_confirmation'), 'Review completed repair'))
        groups.append(('overdue_repairs', jobs.filter(due_at__lt=now, status__in=['assigned', 'awaiting_provider', 'in_progress']), 'Follow up overdue repair'))
        for kind, queryset, action in groups:
            counts[kind] = queryset.count()
            for job in queryset.order_by('due_at', 'pk')[:4]:
                tasks.append({'id': f'{kind}-{job.pk}', 'title': job.issue, 'detail': f'{action} · {job.property.name} / {job.unit.unit_number if job.unit_id else "Shared space"}', 'href': '/dashboard/maintenance', 'kind': kind, 'due_at': job.due_at})
        inspections = inspection_scope(request.user)
        upcoming = inspections.filter(status__in=['awaiting_confirmation', 'scheduled'], scheduled_at__gte=now, scheduled_at__lte=now + timedelta(days=7))
        overdue = inspections.filter(status__in=['awaiting_confirmation', 'scheduled'], scheduled_at__lt=now)
        counts['upcoming_inspections'], counts['overdue_inspections'] = upcoming.count(), overdue.count()
        for kind, queryset in [('overdue_inspections', overdue), ('upcoming_inspections', upcoming)]:
            for inspection in queryset.select_related('unit', 'unit__property').order_by('scheduled_at', 'pk')[:4]:
                tasks.append({'id': f'{kind}-{inspection.pk}', 'title': 'Inspection appointment', 'detail': f'{inspection.unit.property.name} / {inspection.unit.unit_number} · {inspection.status.replace("_", " ")}', 'href': '/dashboard/unit-inspections', 'kind': kind, 'due_at': inspection.scheduled_at})
    response = Response({'counts': counts, 'tasks': tasks[:12], 'total': sum(counts.values()), 'generated_at': now})
    response['Cache-Control'] = 'private, no-store'
    return response
