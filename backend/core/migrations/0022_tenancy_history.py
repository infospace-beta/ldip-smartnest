from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('core', '0021_prepare_workflows')]
    operations = [
        migrations.AlterField(
            model_name='tenant', name='user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                    related_name='tenancies', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddConstraint(
            model_name='tenant',
            constraint=models.UniqueConstraint(fields=('user',), condition=models.Q(status__in=['active', 'expiring']),
                                               name='one_active_tenancy_per_user'),
        ),
    ]
