"""Create an encrypted local snapshot after the operator pauses API and worker writes."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from dotenv import load_dotenv

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--private-root',type=Path,required=True)
parser.add_argument('--quiesced',action='store_true',help='Confirm API, worker and all administrative writers are paused.')
args=parser.parse_args()
if not args.quiesced:
    parser.error('Pause all application writers and pass --quiesced. No backup was taken.')
private=args.private_root.resolve()
secret_file=private/'secrets'/'backup.env'
if not secret_file.is_file():
    parser.error('The separate backup key file is missing. Do not replace an existing lost key.')
load_dotenv(secret_file,override=False)
if os.name=='nt' and 'PG_BIN' not in os.environ:
    candidate=Path(os.environ.get('ProgramFiles',r'C:\Program Files'))/'PostgreSQL/16/bin'
    if candidate.is_dir():os.environ['PG_BIN']=str(candidate)
backend=Path(__file__).resolve().parent.parent/'backend'
sys.path.insert(0,str(backend))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','smartnest_api.settings')
import django
django.setup()
from core.recovery import make_backup
snapshot=private/'backups'/f"smartnest_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.snbackup"
result=make_backup(snapshot)
print(f"Encrypted backup created with {result['included']} stored uploads and {result['missing']} missing references. Key hidden.")
