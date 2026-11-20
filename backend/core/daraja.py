"""Sandbox-only Daraja transport. No production URL or rent-ledger mutation exists here."""
import base64
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from django.conf import settings
from django.utils import timezone


class DarajaUnavailable(Exception):
    pass


class DarajaSandbox:
    base_url = 'https://sandbox.safaricom.co.ke'

    def __init__(self):
        if not settings.DARAJA_SANDBOX_ENABLED or settings.DARAJA_ENV != 'sandbox':
            raise DarajaUnavailable('Daraja sandbox is not configured.')

    def _request(self, path, *, token=None, data=None, basic=None):
        headers = {'Content-Type':'application/json'}
        if basic:
            headers['Authorization'] = 'Basic ' + base64.b64encode(basic.encode()).decode()
        elif token:
            headers['Authorization'] = f'Bearer {token}'
        request = Request(self.base_url + path, headers=headers,
            data=json.dumps(data).encode() if data is not None else None,
            method='POST' if data is not None else 'GET')
        try:
            with urlopen(request, timeout=15) as response:
                result = json.load(response)
            if not isinstance(result, dict):
                raise ValueError('Invalid provider response')
            return result
        except (HTTPError, URLError, TimeoutError, ValueError, OSError):
            # Never put credentials, phone numbers or upstream bodies in application errors.
            raise DarajaUnavailable('The Daraja sandbox could not confirm the request. Check its status before trying again.') from None

    def _credentials(self):
        result = self._request('/oauth/v1/generate?grant_type=client_credentials',
            basic=f'{settings.DARAJA_CONSUMER_KEY}:{settings.DARAJA_CONSUMER_SECRET}')
        token = result.get('access_token')
        if not isinstance(token, str) or not token:
            raise DarajaUnavailable('The sandbox access token could not be obtained.')
        timestamp = timezone.localtime(timezone.now()).strftime('%Y%m%d%H%M%S')
        password = base64.b64encode(f'{settings.DARAJA_SHORTCODE}{settings.DARAJA_PASSKEY}{timestamp}'.encode()).decode()
        return token, timestamp, password

    def start(self, attempt):
        token, timestamp, password = self._credentials()
        callback = f'{settings.DARAJA_CALLBACK_BASE_URL}/api/payments/mpesa/callback/{attempt.pk}/{attempt.callback_secret}/'
        return self._request('/mpesa/stkpush/v1/processrequest', token=token, data={
            'BusinessShortCode':settings.DARAJA_SHORTCODE, 'Password':password, 'Timestamp':timestamp,
            'TransactionType':'CustomerPayBillOnline', 'Amount':int(attempt.amount),
            'PartyA':attempt.phone, 'PartyB':settings.DARAJA_SHORTCODE, 'PhoneNumber':attempt.phone,
            'CallBackURL':callback, 'AccountReference':f'SN{attempt.pk.hex[:10]}',
            'TransactionDesc':'SmartNest sandbox test',
        })

    def query(self, attempt):
        token, timestamp, password = self._credentials()
        return self._request('/mpesa/stkpushquery/v1/query', token=token, data={
            'BusinessShortCode':settings.DARAJA_SHORTCODE, 'Password':password,
            'Timestamp':timestamp, 'CheckoutRequestID':attempt.checkout_request_id,
        })
