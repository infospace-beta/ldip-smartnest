# SmartNest backend setup

## Supabase authentication

Install the pinned dependencies with `python -m pip install -r requirements.txt`. Copy `.env.example` to `.env.local`, set the Supabase publishable key, and keep `SUPABASE_AUTH_ENABLED=true`. The workspace's ignored `.env.local` already selects the SmartNest project `xegzolizugoyuucoixzp`. Process environment variables take precedence. Continue supplying the private `DJANGO_SECRET_KEY` as described below.

Run `python manage.py migrate` and restart Django after enabling Supabase. Migration `0016_user_supabase_identity` adds a nullable unique UUID and preserves existing users and permissions. When enabled, the API accepts Supabase tokens only; the old registration, login, refresh and password endpoints are disabled. Supabase Auth validates the bearer token on every request, so a local role or disabled-account change takes effect immediately. A provider outage returns 503 and never grants access.

For an existing account, first create/confirm its Auth identity in the Supabase dashboard. Verify its email and UUID there, then run:

```powershell
python manage.py link_supabase_user person@example.com <verified-supabase-user-uuid>
```

This explicit administrative step preserves the user's Django role, tenant linkage and portfolio assignments. It refuses to overwrite an existing different link. Never link identities solely because an untrusted requester supplies a matching email. Team onboarding uses approved account invitations; manual role controls remain available to administrators. No service-role key is needed in the app.

All new accounts require an approved invitation. Tenant invitations are accepted only after check-in and email confirmation in Supabase. Public tokenless legacy signup is rejected. Email-only tenancy linking cannot grant access to historical unverified pending accounts. Production requires Supabase with privileged MFA; the legacy mode remains only for isolated compatibility/testing. Verified Supabase linking invalidates the old local password.

Set DB_NAME, DB_USER, DB_PASSWORD, DB_HOST and DB_PORT in the ignored local environment; database credentials are no longer in source. For public deployment use the production configuration example and [production runbook](../docs/PRODUCTION_SECURITY.md), including private storage, separate notice encryption keys, supervised services, backup/restore, monitoring and legal release requirements.

Run these commands from `backend`:

First generate a private signing key once, store it in your local environment or
deployment secret manager, and set `DJANGO_SECRET_KEY` in every backend process.
For a temporary local PowerShell session (with Python on PATH):

```powershell
$env:DJANGO_SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Keep the same key across workers and restarts. Never commit it. Startup fails if
the value is missing, shorter than 50 characters, or uses the insecure development
prefix. Deploying a new key invalidates existing JWTs, sessions and password-reset
links; users must sign in again. Do not retain the old committed key as a fallback.

```powershell
python manage.py migrate
python manage.py runserver
```

In development, password-reset email is printed in the Django terminal. Set `FRONTEND_URL` to the address shown by Next.js (for example `http://localhost:3001`) so the reset link opens the correct frontend.

For real email delivery, configure these environment variables in the backend deployment:

- `DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`
- `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`
- `EMAIL_USE_TLS=true` (or `false` for a provider that does not use STARTTLS)
- `DEFAULT_FROM_EMAIL`
- `FRONTEND_URL` (the public HTTPS origin of the frontend)

Do not commit email credentials. In production, set `DJANGO_ENV=production` and follow the production runbook. Supabase sends account recovery email when Supabase Auth is enabled.

After applying the property ownership migration, an administrator assigns existing properties to managers from **Users & access**. Newly created properties belong to the manager who creates them.

Managers can create or regenerate a seven-day tenant invitation link from a tenant profile. Staff can do this for tenants within the portfolio of the manager who onboarded them, plus any units an administrator assigns directly. Share the link using a trusted channel. Repeated preparation reuses a still-valid invitation; expired invitations can be renewed.

Staff accounts inherit the properties owned by the manager who created them, so onboarding does not require manual unit assignment. Staff can work with tenants, leases, inspections, move events, and maintenance for that scope, but payments and expenses remain manager-only. Maintenance accounts only receive work orders assigned to them and see the contact details needed to complete those jobs.

Profile and handover photos are stored using Django's configured file storage and are served through authenticated, access-checked API routes. Configure durable private storage for production and include it in backups; do not expose the upload directory as a public static/media directory.

Maintenance provider access requires an explicit `assigned_to` account link.
Legacy `assignee` text is display-only: review those jobs and select the intended
provider account through the manager workflow. Names are never automatically
converted to account permissions.

Run the backend tests against an isolated in-memory SQLite database (with the
private `DJANGO_SECRET_KEY` set as above):

```powershell
python manage.py test --settings=smartnest_api.test_settings
```
