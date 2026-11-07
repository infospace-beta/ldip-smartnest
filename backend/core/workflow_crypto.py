"""Authenticated server-side encryption. Keep SECRET_KEY stable and backed up."""
import base64
import hashlib
import hmac
import json
from cryptography.fernet import Fernet, MultiFernet
import os
from django.conf import settings


def cipher():
    keys = [key.strip() for key in os.getenv('NOTICE_ENCRYPTION_KEYS', '').split(',') if key.strip()]
    if keys:
        return MultiFernet([Fernet(key.encode()) for key in keys])
    key = hmac.new(settings.SECRET_KEY.encode(), b'smartnest-notices-v1', hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def seal(title, text):
    return cipher().encrypt(json.dumps({'title': title, 'text': text}).encode()).decode()


def unseal(value):
    return json.loads(cipher().decrypt(value.encode()))
