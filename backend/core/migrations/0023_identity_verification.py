from django.db import migrations, models
from django.utils import timezone


def preserve_verified_identities(apps, schema_editor):
    User = apps.get_model('core', 'User')
    Invitation = apps.get_model('core', 'TenantInvitation')
    alias = schema_editor.connection.alias
    User.objects.using(alias).filter(supabase_user_id__isnull=False).update(identity_verified_at=timezone.now())
    for user_id, accepted_at in Invitation.objects.using(alias).filter(
        accepted_at__isnull=False, tenant__user_id__isnull=False,
    ).values_list('tenant__user_id', 'accepted_at').iterator():
        User.objects.using(alias).filter(pk=user_id, identity_verified_at__isnull=True).update(identity_verified_at=accepted_at)


class Migration(migrations.Migration):
    dependencies = [('core', '0022_tenancy_history')]
    operations = [
        migrations.AddField(model_name='user', name='identity_verified_at',
                            field=models.DateTimeField(null=True, blank=True, editable=False)),
        migrations.RunPython(preserve_verified_identities, migrations.RunPython.noop),
    ]
