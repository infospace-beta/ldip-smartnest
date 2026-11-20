"""One Render instance: API and worker share the service's persistent disk."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

def main():
    port=int(os.environ.get('PORT','10000'))
    if not 1 <= port <= 65535:raise SystemExit('Invalid PORT.')
    base=Path(__file__).resolve().parents[1]
    backend=base/'backend'
    # Migrations must be run separately with the maintenance database identity.
    subprocess.run([sys.executable,'-B','manage.py','migrate','--check'],cwd=backend,check=True)
    children=[]
    stopping=False
    def stop(*_):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    try:
        children.append(subprocess.Popen([sys.executable,'-u','-B','manage.py','process_smartnest_automations','--loop','--interval','60'],cwd=backend))
        children.append(subprocess.Popen([sys.executable,'-m','waitress',f'--listen=0.0.0.0:{port}','--trusted-proxy=*','--trusted-proxy-headers=x-forwarded-proto','smartnest_api.wsgi:application'],cwd=backend))
        while not stopping and all(child.poll() is None for child in children):time.sleep(1)
    finally:
        for child in children:
            if child.poll() is None:child.terminate()
        for child in children:
            try:child.wait(timeout=15)
            except subprocess.TimeoutExpired:child.kill();child.wait()
    return 0 if stopping else 1

if __name__=='__main__':raise SystemExit(main())
