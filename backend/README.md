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
