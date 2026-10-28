from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0004_user_registration_consent_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='maintenancejob',
            name='reported_by_user',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='maintenance_requests',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
