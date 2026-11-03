"""Fill missing houses without replacing existing units or tenant assignments."""
from django.db import migrations


def create_missing_houses(apps, schema_editor):
    Property = apps.get_model('core', 'Property')
    Unit = apps.get_model('core', 'Unit')
    database = schema_editor.connection.alias
    for prop in Property.objects.using(database).all().iterator():
        units = Unit.objects.using(database).filter(property_id=prop.pk)
        numbers = set(units.values_list('unit_number', flat=True))
        missing = max(0, prop.total_units - len(numbers))
        next_number = 1
        additions = []
        for _ in range(missing):
            while str(next_number) in numbers:
                next_number += 1
            additions.append(Unit(property_id=prop.pk, unit_number=str(next_number),
                                  unit_type=prop.tag or 'House', rent=prop.monthly_rent or '0', status='vacant'))
            numbers.add(str(next_number))
        Unit.objects.using(database).bulk_create(additions, batch_size=500)
        occupied = units.filter(status='occupied').count()
        Property.objects.using(database).filter(pk=prop.pk).update(
            total_units=units.count(), occupied_units=occupied, status='leased' if occupied else 'vacant',
        )


class Migration(migrations.Migration):
    dependencies = [('core', '0017_onboarding_invitations')]
    operations = [migrations.RunPython(create_missing_houses, migrations.RunPython.noop)]
