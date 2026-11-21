from django.db import migrations


def protect_history(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute("""
        CREATE FUNCTION smartnest_retain_tenancy_history() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'SmartNest retains tenancy and handover history; deletion is disabled.' USING ERRCODE = '55000';
        END;
        $$;
        REVOKE ALL ON FUNCTION smartnest_retain_tenancy_history() FROM PUBLIC;
        CREATE TRIGGER retain_tenants BEFORE DELETE OR TRUNCATE ON tenants FOR EACH STATEMENT EXECUTE FUNCTION smartnest_retain_tenancy_history();
        CREATE TRIGGER retain_tenancy_events BEFORE DELETE OR TRUNCATE ON tenancy_events FOR EACH STATEMENT EXECUTE FUNCTION smartnest_retain_tenancy_history();
    """)


def unprotect_history(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute('DROP TRIGGER retain_tenants ON tenants; DROP TRIGGER retain_tenancy_events ON tenancy_events; DROP FUNCTION smartnest_retain_tenancy_history();')


class Migration(migrations.Migration):
    dependencies = [('core', '0026_retain_tenancy_history')]
    operations = [migrations.RunPython(protect_history, unprotect_history)]
