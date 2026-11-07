from datetime import timedelta
from decimal import Decimal
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from .models import (User, Property, Tenant, Unit, Notice, NoticeReceipt, MaintenanceJob, MaintenanceOffer,
                     WorkflowPolicy, UnitInspection, InspectionPhoto)
from .serializers import MaintenanceJobSerializer, validate_image_upload
from .views import SmartNestAuthenticated, OwnProfileAuthenticated, maintenance_scope, staff_unit_ids, can_contact, assignable_maintenance_users
from .workflow_crypto import unseal
from .workflow_service import (CATEGORIES, notify, policy_for, providers, approve, offer_next,
                              submit_request, create_inspection, appointment)


def manager_only(request):
    if request.user.role != 'manager': raise PermissionDenied('Only the property manager can perform this action.')


def job_data(job, user):
    data=dict(MaintenanceJobSerializer(job).data)
    p=policy_for(job.property.owner) if job.property.owner_id else None
    suggestion=providers(job,p).first() if p and user.role=='manager' else None
    if p and user.role=='manager' and job.quote_amount is not None and job.assigned_to_id:
        suggestion=providers(job,p).filter(pk=job.assigned_to_id).first() or suggestion
    data.update(category=job.category,description=job.description,requires_quotation=job.requires_quotation,
        suggested_provider={'id':suggestion.pk,'username':suggestion.username} if suggestion else None,
        visit_at=job.visit_at,due_at=job.due_at,completion_notes=job.completion_notes,
        has_completion_photo=bool(job.completion_photo),tenant_response=job.tenant_response,
        conversation_id=job.conversation_id,approved_budget=job.approved_budget,
        contact={'name':job.reported_by,'phone':job.reported_by_user.phone if job.reported_by_user else '',
                 'email':job.reported_by_user.email if job.reported_by_user else ''},
        offer_expires_at=job.offers.filter(status='pending').values_list('expires_at',flat=True).first(),
        inspection_photos=[{'id':photo.pk,'caption':photo.caption} for source in job.source_inspections.all() for photo in source.photos.all()])
    return data


class RequestInput(serializers.Serializer):
    issue=serializers.CharField(max_length=200)
    description=serializers.CharField(max_length=10000,allow_blank=True,required=False,default='')
    category=serializers.ChoiceField(choices=CATEGORIES,default='general')
    priority=serializers.ChoiceField(choices=['low','medium','high'],default='medium')
    requires_quotation=serializers.BooleanField(default=False)
    damage_photo_upload=serializers.FileField(required=False)
    def validate_damage_photo_upload(self,value): return validate_image_upload(value)


@api_view(['GET','POST'])
@permission_classes([SmartNestAuthenticated])
def maintenance(request):
    if request.method=='GET':
        return Response([job_data(j,request.user) for j in maintenance_scope(MaintenanceJob.objects.select_related('property','unit','reported_by_user','assigned_to'),request.user)])
    if request.user.role in ('manager','staff') and not request.data.get('tenant'):
        # Preserve manual work-order entry for older records, with portfolio checks.
        s=MaintenanceJobSerializer(data=request.data);s.is_valid(raise_exception=True)
        prop=s.validated_data['property'];unit=s.validated_data.get('unit')
        if request.user.role=='manager' and prop.owner_id!=request.user.pk:raise PermissionDenied()
        if request.user.role=='staff' and (not unit or unit.pk not in staff_unit_ids(request.user)):raise PermissionDenied()
        target=s.validated_data.get('assigned_to')
        if target and not assignable_maintenance_users(request.user).filter(pk=target.pk).exists():raise ValidationError('Choose a provider linked to this portfolio.')
        job=s.save(status='pending_approval',assigned_to=None,assignee='Property management')
        if request.user.role=='manager':approve(job,request.user,target)
        elif prop.owner:notify([prop.owner],'Repair approval needed',job.issue,link='/dashboard/maintenance')
        return Response(job_data(job,request.user),status=201)
    if request.user.role=='tenant':
        tenant=get_object_or_404(Tenant,user=request.user,unit__isnull=False,unit__status='occupied',status__in=['active','expiring'])
    elif request.user.role=='manager':
        tenant=get_object_or_404(Tenant,pk=request.data.get('tenant'),property__owner=request.user,unit__status='occupied',status__in=['active','expiring'])
    else:raise PermissionDenied('Use a tenant or inspection report to start this request.')
    s=RequestInput(data=request.data);s.is_valid(raise_exception=True);values=dict(s.validated_data)
    values['photo']=values.pop('damage_photo_upload',None)
    job,created=submit_request(tenant,**values)
    data=job_data(job,request.user);data['linked_existing']=not created
    return Response(data,status=201 if created else 200)


@api_view(['GET','PATCH'])
@permission_classes([SmartNestAuthenticated])
def maintenance_detail(request,pk):
    job=get_object_or_404(maintenance_scope(MaintenanceJob.objects.all(),request.user),pk=pk)
    if request.method=='PATCH':
        if request.user.role not in ('manager','staff'):raise ValidationError('Use the repair workflow actions to change a request.')
        if 'property' in request.data or 'unit' in request.data:
            raise PermissionDenied('A repair stays linked to its original home and tenancy.')
        if any(k not in ('issue','priority','description','manager_notes') for k in request.data):raise ValidationError('Use approval or assignment actions to change the repair status or provider.')
        s=MaintenanceJobSerializer(job,data=request.data,partial=True);s.is_valid(raise_exception=True);s.save()
    return Response(job_data(job,request.user))


class JobAction(serializers.Serializer):
    assigned_to=serializers.IntegerField(required=False,min_value=1)
    note=serializers.CharField(required=False,allow_blank=True,max_length=5000,default='')
    reason=serializers.CharField(required=False,allow_blank=True,max_length=5000,default='')
    visit_at=serializers.DateTimeField(required=False)
    completion_notes=serializers.CharField(required=False,max_length=10000,allow_blank=True,default='')
    completion_photo=serializers.FileField(required=False)
    quote_amount=serializers.DecimalField(required=False,max_digits=12,decimal_places=2,min_value=Decimal('0'))
    def validate_completion_photo(self,value):return validate_image_upload(value,'Completion photos')


@api_view(['POST'])
@permission_classes([SmartNestAuthenticated])
@transaction.atomic
def maintenance_action(request,pk,action):
    job=get_object_or_404(maintenance_scope(MaintenanceJob.objects.select_for_update(of=('self',)),request.user),pk=pk)
    s=JobAction(data=request.data);s.is_valid(raise_exception=True);v=s.validated_data
    p=policy_for(job.property.owner)
    if action in ('approve','reject','reassign','resolve-dispute'):
        manager_only(request)
        if action in ('approve','reject') and job.status not in ('pending_approval','logged'):raise ValidationError('This request is not awaiting approval.')
        if action=='approve':
            provider=None
            if v.get('assigned_to'):
                provider=get_object_or_404(providers(job,p),pk=v['assigned_to'])
            approve(job,request.user,provider,v['note'])
        elif action=='reject':
            job.status='rejected';job.manager_notes=v['reason'];job.save(update_fields=['status','manager_notes'])
            notify([job.reported_by_user],'Repair request rejected',f'{job.job_id}: {job.manager_notes}',link='/dashboard/maintenance')
        elif action=='reassign':
            if job.status not in ('assigned','awaiting_provider','in_progress'):raise ValidationError('Only open provider tasks can be reassigned.')
            provider=get_object_or_404(providers(job,p),pk=v.get('assigned_to'))
            job.offers.filter(status='pending').update(status='cancelled')
            offer_next(job,p,provider)
        else:
            if job.status!='disputed':raise ValidationError('No open dispute.')
            job.status='pending_approval';job.manager_notes=v['note'];job.save(update_fields=['status','manager_notes'])
            job.offers.all().delete()
    elif action in ('accept','decline','complete','quote'):
        if request.user.role!='maintenance' or job.assigned_to_id!=request.user.pk:raise PermissionDenied()
        offer=job.offers.filter(provider=request.user,status='pending').first()
        if action in ('accept','decline'):
            if job.status!='assigned' or not offer:raise ValidationError('No pending offer.')
            if action=='accept':
                if offer.expires_at<=timezone.now():raise ValidationError('This offer has expired. Ask your manager for a new assignment.')
                if not v.get('visit_at') or v['visit_at']<=timezone.now():raise ValidationError('Propose a future visit time.')
                job.visit_at=v['visit_at'];job.status='in_progress';offer.status='accepted'
                notify([job.reported_by_user],'Repair visit proposed',f'{job.job_id}: {job.visit_at}. Coordinate access in your repair conversation.',link='/dashboard/maintenance')
                offer.save(update_fields=['status']);job.save(update_fields=['visit_at','status'])
            else:
                offer.status='declined';offer.save(update_fields=['status'])
                if p.enabled and p.auto_reassign:offer_next(job,p)
                else:
                    job.assigned_to=None;job.assignee='Awaiting manager assignment';job.status='awaiting_provider';job.save(update_fields=['assigned_to','assignee','status'])
                    if job.conversation_id:job.conversation.participants.set([job.reported_by_user_id] if job.reported_by_user_id else [])
                    notify([job.property.owner],'Provider declined',f'{job.job_id} needs a new provider.',important=True,link='/dashboard/maintenance')
        elif action=='complete':
            if job.status!='in_progress':raise ValidationError('Accept this task before completing it.')
            if not v['completion_notes'] and not v.get('completion_photo'):raise ValidationError('Add completion details or a photo.')
            job.completion_notes=v['completion_notes'];job.completion_photo=v.get('completion_photo','');job.status='awaiting_confirmation'
            job.save(update_fields=['completion_notes','completion_photo','status'])
            notify([job.reported_by_user],'Please review your repair',f'{job.job_id} is ready for your confirmation.',link='/dashboard/maintenance')
        else:
            if job.status not in ('assigned','in_progress'):raise ValidationError('Cannot submit a quote in this state.')
            if 'quote_amount' not in v:raise ValidationError('Add a quote amount.')
            job.quote_amount=v['quote_amount'];job.quote_notes=v['note'];job.status='pending_approval'
            job.offers.filter(status='pending').update(status='cancelled')
            job.save(update_fields=['quote_amount','quote_notes','status'])
            notify([job.property.owner],'Quotation approval needed',f'{job.job_id}: {job.quote_amount}',link='/dashboard/maintenance')
    elif action in ('confirm','dispute'):
        if request.user.role!='tenant' or job.reported_by_user_id!=request.user.pk:raise PermissionDenied()
        if job.status!='awaiting_confirmation':raise ValidationError('This repair is not awaiting tenant confirmation.')
        job.status='completed' if action=='confirm' else 'disputed';job.tenant_response=v['note'];job.save(update_fields=['status','tenant_response'])
        notify([job.property.owner,job.assigned_to], 'Repair confirmed' if action=='confirm' else 'Repair disputed',
               f'{job.job_id}: {v["note"]}',important=action=='dispute',link='/dashboard/maintenance')
    else: raise ValidationError('Unknown action.')
    return Response(job_data(job,request.user))


@api_view(['GET'])
@permission_classes([SmartNestAuthenticated])
def completion_photo(request,pk):
    job=get_object_or_404(maintenance_scope(MaintenanceJob.objects.all(),request.user),pk=pk)
    if not job.completion_photo:raise ValidationError('No completion photo.')
    return private_photo(job.completion_photo)


def private_photo(field):
    photo=field.open('rb');signature=photo.read(12);photo.seek(0)
    if signature.startswith(b'\xff\xd8\xff'):kind='image/jpeg'
    elif signature.startswith(b'\x89PNG\r\n\x1a\n'):kind='image/png'
    elif signature.startswith(b'RIFF') and signature[8:12]==b'WEBP':kind='image/webp'
    else:
        photo.close();raise ValidationError('The stored photo is not a supported image.')
    response=FileResponse(photo,content_type=kind)
    response['Cache-Control']='private, no-store';response['X-Content-Type-Options']='nosniff'
    return response


class PolicySerializer(serializers.ModelSerializer):
    class Meta:
        model=WorkflowPolicy
        exclude=['id','manager']
        read_only_fields=['last_routine_date','worker_seen_at']
    def validate(self,v):
        def current(k):return v.get(k,getattr(self.instance,k))
        for k in ('provider_response_hours','job_due_hours','inspection_frequency_days','inspection_notice_hours','routine_sample_size'):
            if not 1<=current(k)<=8760:raise ValidationError({k:'Choose a value between 1 and 8760.'})
        if not 0<=current('work_start_hour')<current('work_end_hour')<=23:raise ValidationError('Choose valid working hours.')
        if current('spending_limit')<0:raise ValidationError('Spending limit cannot be negative.')
        days=current('working_days')
        if not isinstance(days,list) or any(type(d)!=int or d not in range(7) for d in days):raise ValidationError('Working days must be weekday numbers 0–6.')
        costs=current('category_costs')
        if not isinstance(costs,dict) or any(k not in CATEGORIES for k in costs):raise ValidationError('Choose valid maintenance categories.')
        try:
            if any(not Decimal(str(c)).is_finite() or Decimal(str(c))<0 or Decimal(str(c))>Decimal('9999999999.99') for c in costs.values()):raise ValueError()
        except Exception:raise ValidationError('Category estimates must be non-negative amounts.')
        mapping=current('provider_categories')
        if not isinstance(mapping,dict):raise ValidationError('Provider categories must map accounts to categories.')
        for key,categories in mapping.items():
            if not str(key).isdigit() or not User.objects.filter(pk=key,role='maintenance',onboarded_by=self.context['request'].user,is_active_user=True).exists():raise ValidationError('Choose providers invited to your portfolio.')
            if not isinstance(categories,list) or any(c not in CATEGORIES for c in categories):raise ValidationError('Choose valid provider categories.')
        inspector=current('inspector')
        manager=self.context['request'].user
        if inspector and not (inspector==manager or inspector.role=='staff' and inspector.onboarded_by_id==manager.pk):raise ValidationError('Choose yourself or your own staff as inspector.')
        return v


@api_view(['GET','PATCH'])
@permission_classes([SmartNestAuthenticated])
def policy(request):
    manager_only(request);p=policy_for(request.user)
    if request.method=='PATCH':
        s=PolicySerializer(p,data=request.data,partial=True,context={'request':request});s.is_valid(raise_exception=True);s.save()
    return Response(PolicySerializer(p).data)


def visible_notices(user):
    q=Q(recipients=user)
    if user.role=='admin':q |= Q(important=True)
    return Notice.objects.filter(q).distinct()


def notice_data(n,user):
    own=n.receipts.filter(user=user).first()
    data={'id':n.pk,'state':n.state,'icon':n.icon,'important':n.important,'created_at':n.created_at,'is_read':bool(own and own.read_at),'protected':not bool(own)}
    if own:
        content=unseal(n.encrypted_content) if n.encrypted_content else {'title':n.title,'text':n.text}
        data.update(content);data['link']=n.link
    else:
        data.update(title='Confidential important notice',text='Only the intended recipients can read this notice.',ciphertext=n.encrypted_content,link='')
    return data


@api_view(['GET','POST'])
@permission_classes([SmartNestAuthenticated])
def notices(request):
    if request.method=='GET':return Response([notice_data(n,request.user) for n in visible_notices(request.user)])
    class Input(serializers.Serializer):
        title=serializers.CharField(max_length=200)
        text=serializers.CharField(max_length=10000)
        recipients=serializers.ListField(child=serializers.IntegerField(min_value=1),allow_empty=False,max_length=200)
        important=serializers.BooleanField(default=False)
    s=Input(data=request.data);s.is_valid(raise_exception=True);v=s.validated_data
    users=list(User.objects.filter(pk__in=set(v['recipients'])))
    if len(users)!=len(set(v['recipients'])) or any(not can_contact(request.user,u) for u in users):raise PermissionDenied('Choose recipients in your permitted contacts.')
    n=notify(users,v['title'],v['text'],important=v['important'],sender=request.user)
    return Response({'id':n.pk,'message':'Notice delivered to the selected recipients.'},status=201)


@api_view(['POST'])
@permission_classes([SmartNestAuthenticated])
def read_notice(request,pk):
    receipt=get_object_or_404(NoticeReceipt,notice_id=pk,user=request.user)
    receipt.read_at=timezone.now();receipt.save(update_fields=['read_at']);return Response({'read':True})


@api_view(['GET'])
@permission_classes([SmartNestAuthenticated])
def unread(request):
    return Response({'unread_count':NoticeReceipt.objects.filter(user=request.user,read_at__isnull=True).count()})


def inspection_scope(user):
    q=UnitInspection.objects.select_related('unit__property','tenant__user','inspector','check_in')
    if user.role=='manager':return q.filter(unit__property__owner=user)
    if user.role=='tenant':return q.filter(tenant__user=user)
    if user.role=='staff':return q.filter(inspector=user,unit_id__in=staff_unit_ids(user))
    return q.none()


class InspectionAuthenticated(OwnProfileAuthenticated):
    def has_permission(self,request,view):
        if request.user.is_authenticated and request.user.role=='tenant':
            # Former tenants retain access to their own condition reports and charge reviews.
            return request.user.is_active and request.user.is_active_user and Tenant.objects.filter(user=request.user).exists()
        return SmartNestAuthenticated().has_permission(request,view)


def inspection_data(i,user,baseline=False):
    data={k:getattr(i,k) for k in ['id','inspection_type','inspection_date','scheduled_at','requested_at','purpose','status','inspector_name','condition','checklist','notes','issues_found','recommended_actions','completed_at','acknowledged_at','agrees_with_report','tenant_comments','proposed_charge','charge_reason','charge_response','charge_comments','maintenance_id']}
    data.update(unit=i.unit_id,unit_number=i.unit.unit_number,property_name=i.unit.property.name,
                tenant=i.tenant_id,tenant_name=i.tenant.name if i.tenant else '',inspector=i.inspector_id,
                photos=[{'id':p.pk,'caption':p.caption} for p in i.photos.all()])
    if not baseline:data['check_in_report']=inspection_data(i.check_in,user,True) if i.check_in and i.check_in.tenant_id==i.tenant_id else None
    return data


class ScheduleInput(serializers.Serializer):
    tenant=serializers.IntegerField(min_value=1)
    inspection_type=serializers.ChoiceField(choices=['move_in','routine','move_out'])
    scheduled_at=serializers.DateTimeField(required=False)


@api_view(['GET','POST'])
@permission_classes([InspectionAuthenticated])
def inspections(request):
    if request.method=='GET':return Response([inspection_data(i,request.user) for i in inspection_scope(request.user)])
    manager_only(request)
    s=ScheduleInput(data=request.data);s.is_valid(raise_exception=True);v=s.validated_data
    tenant=get_object_or_404(Tenant,pk=v['tenant'],property__owner=request.user,unit__isnull=False)
    i=create_inspection(tenant,v['inspection_type'],earliest=v.get('scheduled_at'),force=True)
    return Response(inspection_data(i,request.user),status=201)


class InspectionAction(serializers.Serializer):
    requested_at=serializers.DateTimeField(required=False)
    comments=serializers.CharField(required=False,allow_blank=True,max_length=5000,default='')
    agrees=serializers.BooleanField(required=False)
    checklist=serializers.JSONField(required=False)
    condition=serializers.ChoiceField(choices=['excellent','good','fair','poor'],required=False)
    notes=serializers.CharField(required=False,allow_blank=True,max_length=10000)
    issues_found=serializers.CharField(required=False,allow_blank=True,max_length=10000)
    proposed_charge=serializers.DecimalField(required=False,max_digits=12,decimal_places=2,min_value=Decimal('0'))
    response=serializers.ChoiceField(required=False,choices=['accepted','disputed'])
    photo=serializers.FileField(required=False)
    category=serializers.ChoiceField(choices=CATEGORIES,required=False,default='general')
    def validate_photo(self,value):return validate_image_upload(value,'Inspection photos')
    def validate_checklist(self,value):
        if not isinstance(value,dict) or len(str(value))>20000:raise ValidationError('Use a room, fittings and meter-reading checklist under 20 KB.')
        return value


@api_view(['GET','POST'])
@permission_classes([InspectionAuthenticated])
@transaction.atomic
def inspection_detail(request,pk,action=None):
    i=get_object_or_404(inspection_scope(request.user).select_for_update(of=('self',)),pk=pk)
    if request.method=='GET':return Response(inspection_data(i,request.user))
    s=InspectionAction(data=request.data);s.is_valid(raise_exception=True);v=s.validated_data
    tenant=request.user.role=='tenant' and i.tenant and i.tenant.user_id==request.user.pk
    inspector=request.user.pk==i.inspector_id or request.user.role=='manager'
    if action in ('confirm','reschedule','review','charge-response'):
        if not tenant:raise PermissionDenied()
        if action in ('confirm','reschedule'):
            if i.status not in ('awaiting_confirmation','scheduled'):raise ValidationError('Appointment is no longer awaiting confirmation.')
            if action=='confirm':
                if i.requested_at:raise ValidationError('Wait for your manager to offer the new appointment.')
                i.status='scheduled'
            else:
                if not v.get('requested_at') or v['requested_at']<=timezone.now():raise ValidationError('Choose a future preferred time.')
                i.requested_at=v['requested_at'];i.tenant_comments=v['comments'];i.status='awaiting_confirmation'
                notify([i.unit.property.owner],'Inspection reschedule requested',f'Unit {i.unit.unit_number}: {i.requested_at}',link='/dashboard/unit-inspections')
        elif action=='review':
            if i.status!='awaiting_review':raise ValidationError('This report is not awaiting review.')
            # Acknowledging receipt is separate from accepting findings.
            i.acknowledged_at=timezone.now();i.agrees_with_report=v.get('agrees');i.tenant_comments=v['comments'];i.status='closed'
            if i.agrees_with_report is False:notify([i.unit.property.owner],'Inspection findings disputed',f'Unit {i.unit.unit_number}: {i.tenant_comments}',important=True,link='/dashboard/unit-inspections')
        else:
            if i.proposed_charge is None or not v.get('response'):raise ValidationError('Choose a response to the proposed charge.')
            i.charge_response=v['response'];i.charge_comments=v['comments']
            notify([i.unit.property.owner],'Inspection charge response',f'Unit {i.unit.unit_number}: {i.charge_response}. {i.charge_comments}',important=i.charge_response=='disputed',link='/dashboard/unit-inspections')
    elif action in ('schedule','complete','publish','photo','maintenance','charge'):
        if not inspector:raise PermissionDenied()
        if action=='schedule':
            manager_only(request)
            if i.status not in ('awaiting_confirmation','scheduled'):raise ValidationError('Cannot reschedule a completed inspection.')
            earliest=v.get('requested_at') or i.requested_at
            if not earliest:raise ValidationError('Choose an appointment time.')
            i.scheduled_at=appointment(policy_for(request.user),earliest);i.inspection_date=i.scheduled_at.date();i.requested_at=None;i.status='awaiting_confirmation';i.reminded_at=None
            notify([i.tenant.user if i.tenant else None,i.inspector],'New inspection appointment',str(i.scheduled_at),link='/dashboard/unit-inspections')
        elif action in ('complete','photo'):
            if i.status!='scheduled':raise ValidationError('The tenant must confirm the appointment first.')
            if action=='photo':
                if not v.get('photo'):raise ValidationError('Choose a photo.')
                InspectionPhoto.objects.create(inspection=i,image=v['photo'],caption=v['comments'][:200])
            else:
                if not v.get('checklist'):raise ValidationError('Complete the shared condition checklist.')
                for k in ['checklist','condition','notes','issues_found']:
                    if k in v:setattr(i,k,v[k])
                i.completed_at=timezone.now();i.status='completed'
        elif action=='publish':
            if i.status!='completed':raise ValidationError('Complete the report before sharing it.')
            i.status='awaiting_review'
            notify([i.tenant.user if i.tenant else None],'Inspection report ready',f'Please review the report for {i.unit.unit_number}.',link='/dashboard/unit-inspections')
        elif action=='maintenance':
            if not i.tenant or not i.issues_found:raise ValidationError('Record an issue and linked tenant first.')
            if i.status not in ('completed','awaiting_review','closed'):raise ValidationError('Complete the inspection first.')
            if not i.maintenance_id:
                photo=i.photos.first()
                job,_=submit_request(i.tenant,issue=f'Inspection: {i.issues_found}'[:200],description=i.issues_found+'\n'+i.notes,
                    category=v['category'],photo=photo.image.name if photo else None)
                i.maintenance=job
        else:
            manager_only(request)
            if i.inspection_type!='move_out':raise ValidationError('Charges are reviewed separately during check-out.')
            if 'proposed_charge' not in v or not v['comments']:raise ValidationError('Provide an amount and reason for review.')
            i.proposed_charge=v['proposed_charge'];i.charge_reason=v['comments'];i.charge_response='';i.charge_comments=''
            notify([i.tenant.user if i.tenant else None],'Proposed check-out charge',f'{i.proposed_charge}: {i.charge_reason}. Review separately from the condition report.',link='/dashboard/unit-inspections')
    else:raise ValidationError('Unknown inspection action.')
    i.save()
    return Response(inspection_data(i,request.user))


@api_view(['GET'])
@permission_classes([InspectionAuthenticated])
def inspection_photo(request,pk,photo_pk):
    inspection=get_object_or_404(inspection_scope(request.user),pk=pk)
    p=get_object_or_404(InspectionPhoto,inspection=inspection,pk=photo_pk)
    return private_photo(p.image)


@api_view(['POST'])
@permission_classes([SmartNestAuthenticated])
@transaction.atomic
def record_moveout(request,pk):
    manager_only(request)
    tenant=get_object_or_404(Tenant.objects.select_for_update(),pk=pk,property__owner=request.user)
    class Input(serializers.Serializer):
        move_out_at=serializers.DateTimeField()
    s=Input(data=request.data);s.is_valid(raise_exception=True)
    date=s.validated_data['move_out_at']
    if date<=timezone.now():raise ValidationError('Choose a future move-out date.')
    previous_date=tenant.move_out_at
    tenant.move_out_at=date;tenant.save(update_fields=['move_out_at'])
    existing=UnitInspection.objects.filter(tenant=tenant,inspection_type='move_out').exclude(status='closed').first()
    if existing and existing.status in ('awaiting_confirmation', 'scheduled'):
        # Preserve completed reports, but reconfirm a changed future appointment.
        from .workflow_service import appointment, policy_for, notify
        if previous_date != date:
            scheduled = appointment(policy_for(tenant.property.owner), earliest=date)
            existing.scheduled_at = scheduled
            existing.inspection_date = scheduled.date()
            existing.status = 'awaiting_confirmation'
            existing.reminded_at = None
            existing.save(update_fields=['scheduled_at', 'inspection_date', 'status', 'reminded_at'])
            notify([tenant.user, existing.inspector], 'Check-out appointment changed',
                   f'Your check-out inspection is proposed for {scheduled}. Please confirm the new appointment.',
                   link='/dashboard/unit-inspections')
    i=existing or create_inspection(tenant,'move_out',earliest=date)
    return Response({'move_out_at':date,'inspection':inspection_data(i,request.user) if i else None,'message':'Move-out recorded. Inspection automations are disabled; schedule manually.' if not i else 'Move-out recorded and inspection proposed.'})


@api_view(['GET'])
@permission_classes([SmartNestAuthenticated])
def maintenance_inspection_photo(request,pk,photo_pk):
    job=get_object_or_404(maintenance_scope(MaintenanceJob.objects.all(),request.user),pk=pk)
    photo=get_object_or_404(InspectionPhoto,pk=photo_pk,inspection__maintenance=job)
    return private_photo(photo.image)


@api_view(['GET'])
@permission_classes([SmartNestAuthenticated])
def invitation_property_options(request):
    if request.user.role!='admin':raise PermissionDenied()
    return Response(list(Property.objects.values('id','name')))
