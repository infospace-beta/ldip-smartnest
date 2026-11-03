from django.utils.crypto import salted_hmac


def invitation_token(kind, identifier, expires_at):
    # Reconstruct the same invitation without persisting a usable bearer token.
    return salted_hmac('smartnest.invitation', f'{kind}:{identifier}:{expires_at.isoformat()}', algorithm='sha256').hexdigest()


def tenant_checked_in(tenant):
    if not tenant.unit_id or tenant.status not in ('active', 'expiring') or tenant.unit.status != 'occupied':
        return False
    latest = tenant.events.filter(unit_id=tenant.unit_id).order_by('-recorded_at', '-pk').first()
    return bool(latest and latest.action == 'check_in')
