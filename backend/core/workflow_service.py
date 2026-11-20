"""Transactional maintenance, inspection and directed-notice workflow."""
import logging
from datetime import timedelta
from decimal import Decimal
from random import SystemRandom
from uuid import uuid4
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from .models import (User, Unit, Tenant, Notice, NoticeReceipt, MaintenanceJob,
                     MaintenanceOffer, WorkflowPolicy, UnitInspection, Conversation)
from .workflow_crypto import seal

CATEGORIES = ('general', 'plumbing', 'electrical', 'appliances', 'structural', 'security', 'other')
logger = logging.getLogger(__name__)
OPEN_JOBS = ('pending_approval', 'awaiting_provider', 'assigned', 'in_progress', 'awaiting_confirmation', 'disputed', 'logged')


def policy_for(manager):
    return WorkflowPolicy.objects.get_or_create(manager=manager)[0]


def notify(users, title, text, *, important=False, link='', sender=None):
    ids = {u.pk for u in users if u and u.is_active and u.is_active_user}
    if not ids:
        return None
    n = Notice.objects.create(title='', text='', encrypted_content=seal(title, text),
                              important=important, sender=sender, state='delivered', link=link)
    NoticeReceipt.objects.bulk_create([NoticeReceipt(notice=n, user_id=i) for i in ids])
    # bulk_create bypasses m2m_changed; queue the actual directed-notice workflow too.
    from .sms import queue_notice_sms
    queue_notice_sms(sender=None, instance=n, action='post_add', reverse=False, pk_set=ids)
    return n


def providers(job, policy):
    manager = job.property.owner
    if not manager:
        return User.objects.none()
    qs = User.objects.filter(role='maintenance', is_active=True, is_active_user=True).filter(
        Q(onboarded_by=manager) | Q(assigned_maintenance_jobs__property__owner=manager)).distinct()
    # Empty category assignments allow general jobs only. Specific services must be configured.
    eligible = [u.pk for u in qs if (not u.scope_to_assigned_units or u.assigned_units.filter(pk=job.unit_id).exists()) and (job.category == 'general' or job.category in policy.provider_categories.get(str(u.pk), []))]
    return User.objects.filter(pk__in=eligible).annotate(
        workload=Count('assigned_maintenance_jobs', filter=Q(assigned_maintenance_jobs__status__in=OPEN_JOBS))
    ).order_by('workload', 'id')


def conversation_for(job):
    if not job.reported_by_user_id or not job.assigned_to_id:
        return
    if not job.conversation_id:
        job.conversation = Conversation.objects.create(subject=f'{job.job_id}: {job.issue}'[:200],
                                                      created_by=job.property.owner)
        job.save(update_fields=['conversation'])
    # A replaced provider loses access to the request-linked conversation.
    job.conversation.participants.set([job.reported_by_user_id, job.assigned_to_id])


def offer_next(job, policy, provider=None):
    attempted = job.offers.values_list('provider_id', flat=True)
    choices = providers(job, policy)
    target = choices.filter(pk=provider.pk).first() if provider else choices.exclude(pk__in=attempted).first()
    if job.conversation_id:
        job.conversation.participants.set([job.reported_by_user_id] if job.reported_by_user_id else [])
    job.assigned_to = target
    job.assignee = target.username if target else 'Awaiting eligible provider'
    job.status = 'assigned' if target else 'awaiting_provider'
    job.visit_at = None
    job.save(update_fields=['assigned_to', 'assignee', 'status', 'visit_at'])
    if not target:
        notify([job.property.owner], 'Provider required', f'{job.job_id} has no remaining eligible provider. Review the assignment.',
               important=True, link='/dashboard/maintenance')
        return
    MaintenanceOffer.objects.update_or_create(job=job, provider=target,defaults={'status':'pending',
        'expires_at':timezone.now()+timedelta(hours=policy.provider_response_hours)})
    conversation_for(job)
    notify([target], 'New maintenance task', f'{job.job_id}: {job.issue}. Accept and propose a visit time.', link='/dashboard/maintenance')


def approve(job, manager, provider=None, note=''):
    policy = policy_for(job.property.owner)
    job.approved_by = manager
    job.approved_at = timezone.now()
    job.manager_notes = note
    if job.quote_amount is not None:
        job.approved_budget = job.quote_amount
        if job.assigned_to_id and provider is None:
            provider=providers(job,policy).filter(pk=job.assigned_to_id).first()
        if provider:
            job.offers.filter(provider=provider).delete()
    job.due_at = timezone.now()+timedelta(hours=policy.job_due_hours)
    job.save(update_fields=['approved_by','approved_at','manager_notes','approved_budget','due_at'])
    offer_next(job, policy, provider)
    notify([job.reported_by_user], 'Repair approved', f'{job.job_id} was approved. Follow its progress and coordinate in the linked conversation.', link='/dashboard/maintenance')


@transaction.atomic
def submit_request(tenant, *, issue, category='general', description='', priority='medium', photo=None, requires_quotation=False):
    # Serialize duplicate detection for one unit, including simultaneous submissions.
    Unit.objects.select_for_update().get(pk=tenant.unit_id)
    normalized = ' '.join(issue.split())
    previous = MaintenanceJob.objects.filter(unit=tenant.unit, reported_by_user=tenant.user,
                    category=category, issue__iexact=normalized, status__in=OPEN_JOBS).first()
    if previous:
        return previous, False
    job = MaintenanceJob.objects.create(job_id=f'REQ-{uuid4().hex[:10].upper()}', property=tenant.property,
        unit=tenant.unit, reported_by=tenant.name, reported_by_user=tenant.user, issue=normalized,
        description=description, category=category, priority=priority, damage_photo=photo or '',
        requires_quotation=requires_quotation, assignee='Property management', status='pending_approval', date=timezone.localdate())
    manager = tenant.property.owner
    if manager:
        policy = policy_for(manager)
        cost = policy.category_costs.get(category)
        # Costs are entered by the manager, never trusted from a tenant form.
        if policy.enabled and policy.auto_approve and not requires_quotation and cost is not None and Decimal(str(cost)) <= policy.spending_limit:
            job.approved_budget = Decimal(str(cost)); job.save(update_fields=['approved_budget'])
            approve(job, manager)
        else:
            notify([manager], 'Repair approval needed', f'{job.job_id}: {issue}', link='/dashboard/maintenance')
    return job, True


def appointment(policy, earliest=None):
    start = timezone.now()+timedelta(hours=policy.inspection_notice_hours)
    if earliest and earliest > start:
        start = earliest
    start = (timezone.localtime(start)+timedelta(minutes=1)).replace(second=0, microsecond=0)
    days = policy.working_days or [0,1,2,3,4]
    for _ in range(15):
        if start.hour < policy.work_start_hour:
            start = start.replace(hour=policy.work_start_hour, minute=0)
        if start.weekday() in days and start.hour < policy.work_end_hour:
            return start
        start = (start+timedelta(days=1)).replace(hour=policy.work_start_hour, minute=0)
    raise ValueError('No inspection working day configured.')


def create_inspection(tenant, kind='routine', *, earliest=None, source=None, force=False):
    manager = tenant.property.owner
    if not manager or not tenant.unit_id:
        return None
    p = policy_for(manager)
    if not force and not (p.enabled and p.inspections_enabled):
        return None
    if source:
        existing = UnitInspection.objects.filter(source_event=source).first()
        if existing:
            return existing
        if kind=='move_out':
            existing=UnitInspection.objects.filter(tenant=tenant,inspection_type='move_out',source_event__isnull=True).exclude(status='closed').first()
            if existing:
                existing.source_event=source;existing.save(update_fields=['source_event']);return existing
    scheduled = appointment(p, earliest)
    baseline = UnitInspection.objects.filter(tenant=tenant, unit=tenant.unit, inspection_type='move_in').order_by('created_at').first() if kind == 'move_out' else None
    inspector = p.inspector or manager
    if (not inspector.is_active or not inspector.is_active_user or inspector.role not in ('manager','staff')
        or inspector.role=='staff' and inspector.scope_to_assigned_units and not inspector.assigned_units.filter(pk=tenant.unit_id).exists()):
        inspector=manager
    inspection = UnitInspection.objects.create(unit=tenant.unit, tenant=tenant, source_event=source,
        inspection_type=kind, inspector=inspector, inspector_name=inspector.username,
        inspection_date=scheduled.date(), scheduled_at=scheduled,
        purpose={'move_in':'Check-in condition record','move_out':'Check-out condition comparison','routine':'Routine home condition inspection'}[kind],
        checklist={'rooms':'','fittings':'','meter_readings':'','notes':''}, check_in=baseline)
    notify([tenant.user, inspector], 'Inspection appointment proposed',
        f'{inspection.purpose}: {timezone.localtime(scheduled):%d %b %Y %H:%M}. Confirm or request another time.', link='/dashboard/unit-inspections')
    return inspection


def process_automations(now=None):
    now = now or timezone.now()
    counts = {'reassigned': 0, 'reminders': 0, 'inspections': 0, 'failures': 0}
    ids = list(WorkflowPolicy.objects.filter(manager__role='manager', manager__is_active=True,
               manager__is_active_user=True).values_list('pk', flat=True))
    for policy_id in ids:
        try:
            result = _process_policy(policy_id, now)
            for key in ('reassigned', 'reminders', 'inspections'):
                counts[key] += result[key]
        except Exception:
            # Never log notice bodies, credentials or request payloads.
            logger.error('Automation policy failed policy_id=%s', policy_id)
            counts['failures'] += 1
    return counts


def _process_policy(policy_id, now):
    counts = {'reassigned': 0, 'reminders': 0, 'inspections': 0}
    with transaction.atomic():
        p = WorkflowPolicy.objects.select_for_update().select_related('manager').get(pk=policy_id)
        if p.manager.role != 'manager' or not p.manager.is_active or not p.manager.is_active_user:
            return counts
        p.worker_seen_at = now
        if not p.enabled:
            p.save(update_fields=['worker_seen_at']); return counts
        if p.auto_reassign:
            expired = MaintenanceOffer.objects.select_for_update().filter(status='pending', expires_at__lte=now, job__property__owner=p.manager)
            for offer in expired:
                job = MaintenanceJob.objects.select_for_update().get(pk=offer.job_id)
                if job.status != 'assigned' or job.assigned_to_id != offer.provider_id:
                    offer.status='cancelled'; offer.save(update_fields=['status']); continue
                offer.status='expired'; offer.save(update_fields=['status'])
                offer_next(job,p); counts['reassigned']+=1
        if p.reminders:
            for job in MaintenanceJob.objects.select_for_update().filter(property__owner=p.manager,
                due_at__lte=now, status__in=['assigned','in_progress','awaiting_provider','awaiting_confirmation']):
                if job.escalated_at is None:
                    notify([p.manager], 'Overdue repair escalation', f'{job.job_id} is overdue. Review the repair.', important=True, link='/dashboard/maintenance')
                    job.escalated_at=now
                if job.reminder_at is None or job.reminder_at <= now-timedelta(days=1):
                    notify([job.assigned_to,job.reported_by_user], 'Repair reminder', f'Please update {job.job_id}. This repair is overdue.', link='/dashboard/maintenance')
                    job.reminder_at=now; counts['reminders']+=1
                job.save(update_fields=['reminder_at','escalated_at'])
            for i in UnitInspection.objects.select_for_update().filter(unit__property__owner=p.manager,
                status__in=['awaiting_confirmation','scheduled'], scheduled_at__lte=now+timedelta(days=1), reminded_at__isnull=True):
                notify([i.tenant.user if i.tenant else None,i.inspector], 'Inspection reminder',
                    f'{i.purpose}: {i.scheduled_at}. Contact your manager if another time is needed.',link='/dashboard/unit-inspections')
                i.reminded_at=now;i.save(update_fields=['reminded_at']);counts['reminders']+=1
        if p.inspections_enabled and p.last_routine_date != timezone.localdate(now):
            cutoff=now-timedelta(days=p.inspection_frequency_days)
            eligible=[]
            for t in Tenant.objects.filter(property__owner=p.manager, status__in=['active','expiring'],unit__status='occupied').select_related('unit','property','user'):
                if not UnitInspection.objects.filter(unit=t.unit).filter(Q(created_at__gte=cutoff)|~Q(status='closed')).exists():
                    eligible.append(t)
            SystemRandom().shuffle(eligible)
            for t in eligible[:p.routine_sample_size]:
                if create_inspection(t): counts['inspections']+=1
            p.last_routine_date=timezone.localdate(now)
        p.save(update_fields=['last_routine_date','worker_seen_at'])
    return counts
