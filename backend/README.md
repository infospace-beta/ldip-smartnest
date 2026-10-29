# SmartNest backend setup

Run these commands from `backend`:

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

Do not commit email credentials. In production, set `DEBUG=false` and explicitly configure the frontend origin and email provider.

After applying the property ownership migration, an administrator assigns existing properties to managers from **Users & access**. Newly created properties belong to the manager who creates them.

Managers can create or regenerate a seven-day tenant invitation link from a tenant profile. Staff can do this for tenants within the portfolio of the manager who onboarded them, plus any units an administrator assigns directly. Share the link using a trusted channel; generating a replacement invalidates the previous link.

Staff accounts inherit the properties owned by the manager who created them, so onboarding does not require manual unit assignment. Staff can work with tenants, leases, inspections, move events, and maintenance for that scope, but payments and expenses remain manager-only. Maintenance accounts only receive work orders assigned to them and see the contact details needed to complete those jobs.

Profile and handover photos are stored using Django's configured file storage and are served through authenticated, access-checked API routes. Configure durable private storage for production and include it in backups; do not expose the upload directory as a public static/media directory.
