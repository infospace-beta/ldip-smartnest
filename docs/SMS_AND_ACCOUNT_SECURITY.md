# Account security and SMS setup

Updated 18 November 2026. These changes are local and have not been deployed.

## Sign-in and optional verification

The sign-in page offers Google, LinkedIn OIDC, GitHub, email/password and magic-link sign-in. Social providers require activation in Supabase; their real authorization is not claimed until tested with configured accounts. SMS sign-in appears only when phone authentication is enabled. Passkey sign-in is not offered. See LOCAL_LAUNCH_HANDOFF.md for the current status.

Every role can open Dashboard → Settings. Two-step verification is off by default, including for administrators and managers. A dismissible recommendation appears in the dashboard until dismissed or an authenticator is enabled. Enabling or disabling verification requires a freshly verified authenticator session. Once enabled, the API enforces it for that user regardless of role. The `/security` page handles the challenge after sign-in for users who opted in.

Authenticator secrets and QR codes are managed by Supabase. Disabling the SmartNest requirement leaves the enrolled authenticator in Supabase so it can be enabled again; it does not delete provider factors or weaken any separate Supabase policy.

Backup email is a separate, verified recovery contact. It is not a second Supabase sign-in identity, an email-based second factor, or an automatic password-reset route. Recovery remains administrator-assisted. Sending verification requires a real Django SMTP service; console delivery is intentionally unavailable for this feature. Codes expire in 10 minutes, have a maximum of five attempts, and are stored only as keyed digests. New requests have a one-minute cooldown and security actions are throttled. Use a shared rate-limit cache when scaling beyond one backend process; the default in-memory cache is per process.

## Activate Google

Create a Google OAuth web client in your Google Cloud project. Enter its client ID and secret in Supabase Auth → Providers → Google, and enable that provider. Use the exact callback URL shown by Supabase. Add the real frontend `/auth/callback` URL to the allowed redirects, and the production origin to Google’s allowed origins. Test the consent screen with your intended accounts. SmartNest still requires an invitation or an explicitly linked existing account.

See [Supabase Google setup](https://supabase.com/docs/guides/auth/social-sign-in/auth-google).

## Recommended SMS provider: Twilio for the first release

Twilio is supported by Supabase for phone OTP and by the new Django notification adapter. One provider reduces integration work; confirm Kenya coverage, sender registration, delivery, and pricing before funding an account. No provider account, paid subscription, live SMS, or external message was created during this work.

1. Create and verify your Twilio account yourself. Review its terms and pricing, configure a suitable sender/Messaging Service, enable the destination countries you need, and set usage alerts/limits.
2. In Supabase Auth, configure the supported Twilio SMS provider and enable phone sign-in. Provider credentials stay in Supabase. Set OTP expiry, resend limits and abuse controls there. Test with an account that already has a confirmed primary email and a linked SmartNest invitation/identity; phone-only self-registration is not supported by the current backend identity policy.
3. Put notification credentials in the backend secret environment, never a `NEXT_PUBLIC_` variable:

   ```env
   SMARTNEST_SMS_ENABLED=true
   TWILIO_ACCOUNT_SID=your_account_sid
   TWILIO_AUTH_TOKEN=your_private_auth_token
   TWILIO_MESSAGING_SERVICE_SID=your_messaging_service_sid
   ```

4. Restart Django and the supervised automation worker. Sign in, open Settings, verify your phone through Supabase, and opt in to property SMS notifications. Configuring phone OTP does not itself enable notification SMS.
5. Check queued counts without sending: `python manage.py process_smartnest_sms --dry-run`. After an explicitly approved test notification, use `python manage.py process_smartnest_sms --limit 1` or the normal automation worker. Worker passes process SMS only when SMS delivery is enabled.

Notification SMS contains only a generic notice and a workspace link. It excludes notice bodies, rent amounts, photos and other property details. Only explicitly opted-in users with provider-verified phones are queued. Removing consent or disabling an account skips pending messages. Notices older than 24 hours are skipped. The unique notice/user pair prevents repeat submissions for the same notice. An accepted Twilio submission is not proof of handset delivery. Configure provider delivery monitoring before release. Ambiguous outcomes and interrupted `sending` rows require provider reconciliation; they are not automatically retried, to avoid duplicate messages and charges. This adapter does not yet synchronize carrier STOP opt-outs; configure provider-side opt-out enforcement and test it before enabling production notifications.

For higher Kenya-only volumes, compare Africa’s Talking as a later alternative. A Supabase Send SMS hook and another notification adapter would be required; that alternative is not implemented here.

References: [Supabase phone login](https://supabase.com/docs/guides/auth/phone-login), [Twilio Messages API](https://www.twilio.com/docs/messaging/api/message-resource).

## Email delivery

Configure Django’s SMTP `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_PORT`, TLS, and a verified `DEFAULT_FROM_EMAIL` to deliver backup-email codes. Configure Supabase’s custom SMTP separately for invitations, confirmations, and password recovery. A working Django SMTP connection does not configure Supabase email, or vice versa. Test delivery using addresses you control, without putting codes or secrets into logs.

## Daraja: recommended next integration

Use a dedicated Django payment service and start with Daraja sandbox. Keep consumer credentials and passkeys server-side. Use an authorized Paybill/Till setup appropriate to the landlord/manager receiving funds; do not silently collect different landlords’ funds into the platform’s own account.

For an STK Push flow, create a pending payment attempt on the server using the authenticated tenancy and server-calculated amount, then initiate the request with a unique reference. A prompt or successful initiation is not a paid invoice. Receive asynchronous results on a public HTTPS callback, correlate provider request identifiers with the saved attempt, and reconcile against provider query/settlement records. Handle cancellations, timeouts, missing callbacks and duplicate callbacks idempotently; use a unique receipt constraint and an atomic ledger update. Do not trust browser-supplied success, amount or tenant IDs, or invent a provider callback signature scheme. Confirm the supported callback validation and query APIs in the current Daraja portal before implementation.

A disabled-by-default Daraja sandbox flow is now prepared and tested with mocked provider calls. It never records real rent payments. The separate production payment workflow still records payment references; no money was moved. You will need the business account details, approved shortcode, appropriate product access, credentials, callback domain and settlement/reconciliation policy before a live integration.

References: [Safaricom Daraja portal](https://developer.safaricom.co.ke/), [Safaricom integration overview](https://www.safaricom.co.ke/images/Downloads/Tender_Documents/EOI_Safaricom_M-PESA_Integration_V1_002.pdf).
