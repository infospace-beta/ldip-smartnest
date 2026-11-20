# SmartNest local launch preparation

Updated 18 November 2026. This is the current handoff and supersedes the earlier provider/worker/storage status in the deployment review. No production host, paid provider account or live payment was created.

## Stored data and persistence

There is no age-based deletion of saved users, properties, tenancies, payments, notices or uploads in the reviewed application. A regression test creates ten-year-old records, runs the automation worker twice, and verifies that records remain queryable and the uploaded file is unchanged. Sessions, invitations and login links can expire without deleting those records. SMS deliveries more than 24 hours old can be skipped, but the saved notice and delivery record are not deleted. Explicit property/account deletion can cascade to related records; that is a consequence of the authorized delete action, not an age-based purge.

The application still uses PostgreSQL `ldip_db` on port 5432. Logging out or restarting the application does not reset the database. Changing the database host/name selects a different dataset; never deploy by flushing or recreating the existing production database.

Uploads now use this persistent local directory, outside the Git checkout:

`C:\Users\HP\Documents\Codex\SmartNest-private\media`

The path is configured in the ignored `backend/.env.local`. All four existing photos were copied and verified with SHA-256. Original copies were preserved. They were removed from the current Git index, so the checkout now stages their removal from tracking; no commit or history rewrite was made. Old Git history can still contain them. New uploads, including inspections and maintenance photos, use the external media root. All known upload directories, including older unreferenced files, are included in encrypted backups.

One actual encrypted backup was created under `SmartNest-private\backups`. Its encryption key is in the separate restricted file `SmartNest-private\secrets\backup.env`; it was not printed or committed. The private directory is restricted to the current Windows user and SYSTEM. Keep a separate secure copy of this encryption key; the backup cannot be recovered without it.

The backup was restored to the separate database `smartnest_restore_20261118_093641`, with restored files under the private `restore-rehearsals` directory. All **21 core table counts**, **four upload checksums**, and the recovered signing key matched. No live database was overwritten, no missing references were tolerated, and the live account remained unchanged.

Snapshots are not automatically pruned. App deletion affects active records; earlier backup snapshots can retain old copies until an administrator deletes them under the chosen retention policy. Monitor disk capacity and arrange offsite backups before production. A local backup alone cannot protect against loss of the PC or its disk.

## Local worker and health

The existing Windows worker supervisor is running and restarts its worker child if it exits. The API readiness endpoint now returns HTTP 200. The current supervisor lasts for the Windows session; no startup task or OS service was installed, so restart it after a PC reboot if necessary:

```powershell
& "C:\Program Files\PowerShell\7\pwsh.exe" -NoProfile -File .\deploy\supervise-worker.ps1 -PythonPath "C:\Users\HP\AppData\Local\Programs\Python\Python314\python.exe"
```

The supervisor uses an exclusive lock to avoid duplicate copies. Check before starting it again. Run the health/storage checks from the project directory:

```powershell
python backend/manage.py check_storage --deployment
python backend/manage.py check_operations --backup-dir "C:\Users\HP\Documents\Codex\SmartNest-private\backups"
```

Monitoring checks API/worker readiness, media presence, backup age (26 hours by default), and free disk space (1 GiB minimum by default). It returns a nonzero exit status when unhealthy. Ubuntu monitoring additionally requires a recent successful offsite-transfer marker. These checks report problems; they never delete records, uploads or backups.

To take another consistent local backup, pause the API, worker supervisor/child, and any administrative writers first. Then:

```powershell
python deploy/local-backup.py --private-root "C:\Users\HP\Documents\Codex\SmartNest-private" --quiesced
```

The helper loads the separate key without displaying it. Resume the API and worker afterwards. Do not pass `--quiesced` while writes/uploads are still running. The existing restore command refuses the live database and requires an empty `smartnest_restore_*` target.

## Sign-in activation

The page now includes Google, LinkedIn OIDC, GitHub, password and magic-link flows, with provider logos. Password and magic-link modes share the email field; changing to magic-link mode removes the password requirement. Both normal modes fit a 375×667 viewport in Chrome. OAuth handlers use PKCE and the existing callback route. Magic links use `shouldCreateUser:false`, so they cannot become a public-registration bypass. Existing SmartNest invitations and subject-based account linking remain required.

Provider activation is not the same as local code completion. The connected Supabase project currently reports the social providers unavailable. Disabled buttons show that status honestly. No provider authorization, real password, email link delivery or SMS delivery was faked in testing.

For each OAuth app, enter its client ID/secret in Supabase, not in browser code. Use the exact Supabase callback URL shown in its dashboard, typically `https://<project>.supabase.co/auth/v1/callback`. Add each approved frontend `/auth/callback` URL to the Supabase redirect allowlist. Keep `localhost` and `127.0.0.1` consistent across login and callback; PKCE needs the browser’s matching verifier cookie.

| Option | What you must supply |
|---|---|
| Google | Google Cloud OAuth web client, consent-screen setup and approved origins. |
| LinkedIn | LinkedIn app with the OpenID Connect sign-in product and callback configured; enable Supabase `linkedin_oidc`. |
| GitHub | GitHub OAuth App with the Supabase callback; enable the GitHub provider in Supabase. |
| Magic link | Enabled Supabase email provider, production-capable SMTP and a magic-link template with the correct link/token-hash callback. Test delivery and callback in the same browser. |
| Backup email | Configure Django SMTP separately. This remains a verified recovery contact, not another login identity. |

References: [Google](https://supabase.com/docs/guides/auth/social-sign-in/auth-google), [LinkedIn](https://supabase.com/docs/guides/auth/social-sign-in/auth-linkedin), [GitHub](https://supabase.com/docs/guides/auth/social-sign-in/auth-github), [magic links](https://supabase.com/docs/guides/auth/auth-email-passwordless).

## Twilio and notification SMS

The Twilio adapter and outbox are prepared. An additional fix connects actual operational notices to the outbox: the notice service uses `bulk_create`, which bypassed the original many-to-many signal. Both direct recipients and operational notices are now covered by regression tests. The worker processes queued messages only when `SMARTNEST_SMS_ENABLED=true`.

You still need a Twilio account, a suitable sender/Messaging Service, Kenya delivery permissions, spending alerts and tested opt-out handling. Configure Supabase phone OTP separately from Django notification credentials. Users must verify their phones and opt in to property notifications. No OTP, SMS or external notification was sent during this work. Ambiguous delivery outcomes are not blindly retried; reconcile them with provider records before resending. See `SMS_AND_ACCOUNT_SECURITY.md` for the credential names and consent/delivery details.

## Daraja sandbox implementation

A tenant payment screen and these API routes are prepared:

- `GET/POST /api/payments/mpesa/`
- `POST /api/payments/mpesa/<attempt>/query/`
- A per-attempt callback route with an opaque callback identifier.

The server calculates the whole-shilling test amount from the linked tenancy, normalizes Kenyan phone numbers, records an attempt before contacting Daraja, and enforces idempotency and ownership. It handles provider timeouts and duplicate request identifiers without automatically sending another prompt. Callback identifiers must match the saved attempt. A callback alone never confirms a result; an authenticated query must confirm it.

**This is sandbox-only and never inserts a real Payment or marks rent paid.** `DARAJA_ENV=live` is rejected; the transport has only the Safaricom sandbox hostname. Before live payments, implement business settlement rules, receipt verification, duplicate-safe financial ledger updates, audits, reconciliation and the necessary product approvals. The sandbox callback URL’s opaque identifier is not a provider signature.

Required backend secrets: `DARAJA_CONSUMER_KEY`, `DARAJA_CONSUMER_SECRET`, `DARAJA_SHORTCODE`, `DARAJA_PASSKEY`, `DARAJA_CALLBACK_BASE_URL`; enable only with `DARAJA_SANDBOX_ENABLED=true` and `DARAJA_ENV=sandbox`. A public HTTPS callback is required for an actual provider test. None of these live/test credentials existed, so all transport tests used mocks and no STK prompt or money movement occurred.

References: [Safaricom Daraja](https://developer.safaricom.co.ke/), [Safaricom’s SDK request fields](https://github.com/safaricom/mpesa-java-sdk/blob/master/src/main/java/Mpesa.java).

## Ubuntu staging and production preparation

Use one managed Ubuntu host for the existing shared-file design, with managed PostgreSQL and Supabase Auth. Use private persistent `/var/lib/smartnest/media`, `/var/lib/smartnest/worker`, `/var/lib/smartnest/static` and `/var/lib/smartnest/backups` paths; do not keep live uploads inside `/opt/smartnest` or temporary directories. Preserve and restore the current data before switching storage or database settings.

Prepared files:

- Existing API, web and worker services and Nginx TLS/static-routing template.
- `deploy/postgres-roles.sql.example`: separate migration owner and least-privilege runtime account, using an `app` schema. Passwords are entered with psql’s secure `\password` prompt. This template was not run against the local database.
- Backend and frontend production environment examples. Set actual hostnames and secrets before building/releasing. Run migrations with the maintenance account, then run the API/worker using the restricted runtime account. The development `ldip_user` keeps CREATEDB for local use; it is not the recommended production runtime identity.
- `deploy/validate-production.py`: offline configuration validation. It rejects missing/example values without printing secrets. Run it with the real backend/frontend/backup environment files. The supplied examples deliberately fail until filled in.
- `deploy/smartnest-backup.service` and `.timer`: daily at **03:00 Africa/Nairobi**, with a short randomized delay. The script locks against overlapping runs, pauses active app services for a consistent snapshot, resumes them even on failure, and copies only the encrypted archive offsite through a configured rclone remote. No automatic pruning.
- `deploy/smartnest-monitor.service` and `.timer`: five-minute readiness, disk and backup/offsite checks. Configure the actual API Host header in `monitor.env`. It checks the private loopback endpoint using the configured trusted-proxy HTTPS header. Connect service failures/journal output to your chosen alert destination; no external alerts are configured yet.
- Custom 404, robots and sitemap routes. Search indexing defaults off; public indexing requires a real `NEXT_PUBLIC_SITE_URL` and `SMARTNEST_PUBLIC_INDEXING=true` before the production build. Private/account pages remain noindex.

The Ubuntu units were not installed or executed on Linux because no host exists. The Bash backup script passed a syntax check. Review paths, certificates, ownership, permissions, firewall, proxy trust and service behavior on staging before enabling timers. Install PostgreSQL client tools compatible with your managed server, rclone and its private remote configuration. Keep `/etc/smartnest/backup.env` and rclone credentials root-only and keep a separate secure recovery-key copy. Backups need monitoring and periodic restore drills; an archive existing is not sufficient proof of recovery.

## Validation and remaining external work

The final source has 117 backend tests and 23 frontend tests; the completed run passed. TypeScript and production build passed. Lint has no errors and the same two existing unused-variable warnings. An actual local backup/restore drill and live worker/storage checks passed. Social OAuth, magic-link delivery, SMS and Daraja transport were tested locally with mocked providers; real delivery/authorization tests require your accounts and credentials.

No production domain/server, Twilio account or Daraja app exists yet, per your clarification. No paid service, DNS, remote production database, offsite transfer, public uptime alert or live payment was activated. No blanket promise against disk failure or an expired hosting account is possible; persistent storage, verified restore and offsite backups are the protections prepared here.
