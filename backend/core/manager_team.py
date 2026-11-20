import hashlib
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import AccountInvitation, User
from .invitation_tokens import invitation_token
from .views import SmartNestAuthenticated


def private_response(data, status=200):
    response = Response(data, status=status)
    response['Cache-Control'] = 'private, no-store'
    return response


@api_view(['GET'])
@permission_classes([SmartNestAuthenticated])
def manager_team(request):
    if request.user.role != 'manager':
        return private_response({'error': 'Only managers can view their team.'}, 403)
    members = list(User.objects.filter(onboarded_by=request.user, role__in=['staff', 'maintenance']).order_by('username', 'pk'))
    emails = {member.email.casefold() for member in members}
    rows = [{
        'id': f'user:{member.pk}', 'name': member.get_full_name() or member.username,
        'email': member.email, 'phone': member.phone, 'role': member.role,
        'status': 'active' if member.is_active and member.is_active_user else 'inactive',
        'invitation_id': None, 'expires_at': None, 'can_invite': False,
    } for member in members]
    invitations = AccountInvitation.objects.filter(
        created_by=request.user, role__in=['staff', 'maintenance'], accepted_at__isnull=True,
    ).select_related('created_by', 'property', 'unit').order_by('-created_at')
    now = timezone.now()
    for invitation in invitations:
        if invitation.email.casefold() in emails:
            continue
        valid = invitation.issuer_valid()
        rows.append({
            'id': f'invitation:{invitation.pk}', 'name': invitation.name,
            'email': invitation.email, 'phone': invitation.phone, 'role': invitation.role,
            'status': ('expired' if invitation.expires_at <= now else 'pending') if valid else 'unavailable',
            'invitation_id': str(invitation.pk), 'expires_at': invitation.expires_at,
            'can_invite': valid,
        })
    return private_response(rows)


@api_view(['POST'])
@permission_classes([SmartNestAuthenticated])
def manager_team_invitation_link(request, pk):
    if request.user.role != 'manager':
        return private_response({'error': 'Only managers can share team invitations.'}, 403)
    with transaction.atomic():
        invitation = AccountInvitation.objects.select_for_update().filter(
            pk=pk, created_by=request.user, role__in=['staff', 'maintenance'],
        ).first()
        if not invitation:
            return private_response({'error': 'Invitation not found.'}, 404)
        if not invitation.issuer_valid():
            return private_response({'error': 'This invitation is no longer within your property scope.'}, 403)
        if invitation.accepted_at or User.objects.filter(email__iexact=invitation.email).exists():
            return private_response({'error': 'This person already has an account. An invitation is no longer needed.'}, 409)
        if invitation.expires_at <= timezone.now():
            invitation.expires_at = timezone.now() + timedelta(days=7)
        token = invitation_token('account', invitation.pk, invitation.expires_at)
        invitation.token_digest = hashlib.sha256(token.encode()).hexdigest()
        invitation.save(update_fields=['expires_at', 'token_digest'])
    return private_response({'token': token, 'email': invitation.email, 'expires_at': invitation.expires_at})
