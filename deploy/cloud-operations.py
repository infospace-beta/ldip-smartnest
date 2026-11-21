"""Run a private encrypted backup, or check public readiness without logging records."""
import argparse
import io
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit
from urllib.request import urlopen

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('operation', choices=['backup', 'health'])
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]

if args.operation == 'backup':
    from dotenv import load_dotenv
    configuration = os.environ.pop('SMARTNEST_BACKUP_ENV', '')
    if not configuration:
        raise SystemExit('The encrypted Actions configuration is not set. No backup ran.')
    load_dotenv(stream=io.StringIO(configuration), override=True)
    os.environ['PGSSLROOTCERT'] = str(root / 'deploy/supabase/prod-ca-2021.crt')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartnest_api.settings')
    sys.path.insert(0, str(root / 'backend'))
    import django
    django.setup()
    from django.core.management import call_command
    from io import StringIO
    output = StringIO()
    call_command('cloud_backup', stdout=output)
    result = json.loads(output.getvalue())
    call_command('cloud_backup', verify_key=result['key'])
    print('Encrypted offsite backup uploaded, downloaded, decrypted and verified. Existing snapshots were retained.')
else:
    target = os.getenv('SMARTNEST_API_URL', '').rstrip('/')
    parsed = urlsplit(target)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SystemExit('Configure the HTTPS API origin before enabling uptime checks.')
    for attempt in range(3):
        try:
            with urlopen(target + '/api/health/ready/', timeout=90) as response:
                payload = json.load(response)
                if response.status == 200 and payload.get('status') == 'ready':
                    print('SmartNest API and worker are ready.')
                    break
        except Exception:
            pass
        if attempt == 2:
            raise SystemExit('SmartNest readiness check failed after three attempts. Check the hosting dashboard; no private logs are attached.')
        time.sleep(15)
