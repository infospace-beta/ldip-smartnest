from django.db import migrations


def pin_path(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute('ALTER FUNCTION smartnest_retain_tenancy_history() SET search_path = pg_catalog;')


def reset_path(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute('ALTER FUNCTION smartnest_retain_tenancy_history() RESET search_path;')


class Migration(migrations.Migration):
    dependencies = [('core', '0027_prevent_history_deletion')]
    operations = [migrations.RunPython(pin_path, reset_path)]
