from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_property_photo_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='registration_consent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
