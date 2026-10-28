from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_maintenancejob_reported_by_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='unitinspection',
            name='inspection_type',
            field=models.CharField(
                choices=[('routine', 'Routine'), ('move_in', 'Move-in'), ('move_out', 'Move-out')],
                default='routine',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='unitinspection',
            name='checklist',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
