"""Send a minimal service-failure alert; never attach application logs or secrets."""
import os
import re
import sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE','smartnest_api.settings')
import django
django.setup()
from django.conf import settings
from django.core.mail import send_mail
from django.core.validators import validate_email

def main():
    unit=sys.argv[1] if len(sys.argv)==2 else ''
    if not re.fullmatch(r'smartnest-[a-z-]+\.service',unit):raise SystemExit('Invalid service name.')
    recipient=os.getenv('SMARTNEST_ALERT_EMAIL','')
    validate_email(recipient)
    send_mail('SmartNest service failure',f'{unit} failed. Review its systemd journal on the server. No application logs are included.',settings.DEFAULT_FROM_EMAIL,[recipient],fail_silently=False)

if __name__=='__main__':main()
