# SmartNest production and recovery runbook

The application is currently local. These are deployable templates and acceptance steps, not a claim that a public host or ODPC registration already exists.

## Configuration

Use Python 3.14, PostgreSQL, pinned `backend/requirements.txt`, Node supported by Next 16 and `npm ci` in `frontend`. Use `backend/.env.example` locally and `backend/.env.production.example` as the production checklist. Supply secrets outside Git, with restricted OS/service-account permissions.

`DJANGO_ENV=production` defaults DEBUG off and HTTPS/secure cookies/HSTS on. Production startup rejects wildcard/empty hosts, DEBUG, default/superuser database usernames, absent database credentials, insecure database TLS modes, legacy auth, missing notice keys, missing private media directory, and non-HTTPS frontend/origins. Never turn off these controls to get a deployment to start. Inspect `python manage.py check --deploy` against the actual production environment. Use a dedicated restricted database role; the application account must not have SUPERUSER, CREATEDB or CREATEROLE. Run schema migrations with a separate maintenance identity, then restore runtime credentials before starting the services.

HSTS subdomains/preload are deliberate opt-ins. Django warns W005/W021 until enabled: verify all affected subdomains and approve the preload policy before enabling `DJANGO_HSTS_SUBDOMAINS=true` and `DJANGO_HSTS_PRELOAD=true`. The isolated production-check validation enabled both for example domains; it did not alter real DNS or enroll any domain in a preload list.

Create a fresh production database/schema under a migration owner; grant the runtime role CONNECT, schema USAGE, table SELECT/INSERT/UPDATE/DELETE and sequence USAGE/SELECT. Set matching DEFAULT PRIVILEGES for the migration owner for future objects. The runtime role does not own the database/schema/tables. Keep the database private and use verified TLS (`verify-full` and the provider CA) where supported. Production database account provisioning and credential rotation are operator/hosting actions, not completed by committing this runbook.

`MEDIA_ROOT` defaults to the existing backend folder for local compatibility. In production set `DJANGO_MEDIA_ROOT` to private persistent storage, and copy existing referenced `profile-photos` and `tenancy-events` directories there before switching. Never serve media via nginx aliases or a public bucket. Back up every referenced upload directory. Set quotas/alerts at the filesystem/storage layer. Existing tracked photos are not deleted by these changes; remove personal data from source-control history separately using an approved process.

## Notice keys

`NOTICE_ENCRYPTION_KEYS` is a comma-separated Fernet key ring: first key encrypts, all keys decrypt. Keep it separate from the signing key. Existing local notices used an HMAC-derived key. The local upgrade preserves that exact key in the ignored environment file; do not replace it with a random key and lose old messages. For a different deployment, derive the previous key securely from its original signing secret using the algorithm in `workflow_crypto.py`, include it in the key ring, and validate old notices. To rotate, prepend a new key, re-encrypt every old ciphertext under a transaction-controlled maintenance process, verify, then retire old keys only after their backup/retention requirements end. Restoring notices requires the corresponding keys.

## Services and monitoring

For the current Windows session, `deploy/supervise-worker.ps1 -PythonPath <actual-python.exe>` holds an exclusive checkout lock and restarts an exited worker after ten seconds. Its child PID and per-start stdout/stderr logs are under ignored `backend/.runtime/`. It is not an installed Windows service or reboot-start task; use systemd on Linux or register an approved service/task on a chosen Windows production host, with restricted service identity, log rotation and external alerts.

Linux systemd templates are in `deploy/`. Replace paths/domains, create a non-login `smartnest` service identity, restricted `/etc/smartnest/*.env` files and writable private `/var/lib/smartnest` paths. Install the templates only on the chosen production host. The API uses Waitress, not `runserver`. Next is built before `npm run start`. Keep the API, Next and database ports private.

The nginx template overwrites the forwarded HTTPS header; trust it only behind the stated loopback proxy. It disables the separate Django admin route pending its own MFA/private access configuration, refuses public media paths and avoids logging invitation/reset query strings. Configure unknown-host rejection, TLS certificates/renewal, firewall rules and log retention for the actual host. Validate `nginx -t` before reloading. Static files require `collectstatic`.

Worker failures are isolated per manager and retried with a bounded backoff; the policy lock still prevents duplicate concurrent policy processing. The heartbeat advances only after a successful pass. `/api/health/` is process liveness; `/api/health/ready/` checks database access and a fresh worker heartbeat, returning generic 503 on failure. Run external checks at least every minute, alert on sustained failure and service restart loops, and alert on disk, memory, CPU, database connections/locks, backup age and certificate expiry. Readiness does not prove Supabase, SMTP or every storage operation works; monitor those with controlled synthetic/staging checks. Mutation audit logs record actor ID, route template, method and status without payload/query data; forward them to restricted append-only logging with an approved retention policy.

## Backup and restore

Use a PostgreSQL client major version matching the server for dump/restore. Install `pg_dump`/`pg_restore` and set `PG_BIN` if they are not on PATH. Generate a private Fernet `SMARTNEST_BACKUP_KEY` and store it independently from encrypted snapshots. On Windows restrict file/directory ACLs explicitly; POSIX mode bits alone are not a Windows ACL policy.

Pause writes/uploads and the worker during capture (maintenance window), then:

```sh
python manage.py backup_smartnest --quiesced --output /restricted-backups/snapshot.snbackup
```

This snapshots PostgreSQL, every referenced Django upload and notice/signing recovery keys in one encrypted archive with checksums. Missing referenced files abort capture. It does not back up external Supabase Auth users/configuration, SMTP or host configuration: arrange those separately. The implementation buffers archives in memory and is intended for the current small deployment; move to streaming encrypted backups/PITR before large datasets. Restrict temporary-storage access and ensure enough disk/RAM.

If investigating an already-degraded source, `--allow-missing` explicitly records missing paths in the encrypted manifest and warns about incomplete media. It never clears database references or substitutes another file. The local pre-migration snapshot recorded one preexisting missing historical handover photo; all five available referenced uploads and the database/keys were preserved. A same-named file in another month is not proof of identity and was not substituted.

Create a separate empty database whose name starts `smartnest_restore_`, with appropriate restore-owner rights; choose a new private media directory and secrets destination:

```sh
python manage.py restore_smartnest --backup /restricted-backups/snapshot.snbackup --database smartnest_restore_rehearsal --media /restricted-restore/media --secrets /restricted-restore/recovery-secrets.json
```

The command refuses the running database, nonempty targets, live/overlapping media and existing destinations. Restore only trusted backups: database archives are executable database instructions. Compare table counts, file hashes and encrypted notice decryption, then exercise sign-in and private media in an isolated staging environment. An isolated sample-data rehearsal is part of this change's validation. Do not promote a restored database until the responsible operator approves the target and key/configuration changes. Delete plaintext rehearsal secrets/files securely when no longer needed. Test restoration quarterly and after significant schema/storage changes. Define RPO/RTO, retention, encrypted off-site copies and scheduled production backup alerts with the hosting provider; these are not installed on localhost.

## Identity and workflows

Legacy public tenant signup now requires an unused checked-in tenant invitation. Email-only linking additionally requires a trusted Supabase identity or evidence of an accepted invitation, so historical unverified preclaims cannot be promoted. Production requires Supabase. Keep Google/SMS/provider features disabled until properly configured. Do not expose the Django admin as an alternative to API MFA.

Tenancies retain historical account links. Only one active/expiring tenancy per account is allowed at database level. For a returning tenant, check out the former tenancy, choose a vacant house, select the existing-account checkbox and enter the verified account email. The existing login is retained and history remains linked. Simultaneous active leases for the same account are intentionally not enabled. Applying migration 0022 preserves existing data; back up before deployment.

Migration 0023 stores identity verification independently of tenancy/property lifetime and backfills only already-linked Supabase accounts and accepted tenant invitations. Historical unverified accounts are not promoted. Verified Supabase linking also invalidates old local passwords, and legacy login rejects any Supabase-bound account.

## Legal release gate (Kenya)

The public privacy/terms pages use the operator's supplied contact, `ogonyogad@gmail.com`. Full legal-name details are on hold. The operator confirmed no ODPC certificate; the application does not claim one. Before real public operation, complete the legal identity, determine controller/processor roles, obtain applicable ODPC registration, and approve processing/vendor contracts, transfer safeguards and data-subject request procedures. Property management is a mandatory registration category: https://www.odpc.go.ke/faqs/ . Existing real data on localhost still requires appropriate handling.

Finalise a category-specific retention schedule, purposes/lawful bases, incident-response responsibilities and applicable breach timelines. Assess whether a DPIA and submission are required before processing and review inspection notice floors against applicable leases/law. Have the privacy/terms reviewed for actual operations; the pages openly identify pending details and do not substitute for these steps. Keep manager automation opt-outs and manual controls. Target OWASP ASVS Level 2 and WCAG 2.2 AA with evidence; neither this implementation nor a passing build certifies compliance.

## Acceptance

- Production deployment check clean, real HTTPS/cookies/hosts/CORS/headers tested.
- No credentials/private uploads in published source or public storage; least-privilege DB and private admin boundary verified.
- ODPC/operator/legal documents and applicable transfer/DPIA requirements completed.
- Database/files/keys restored and role-based staging journeys pass; monitored worker restarts after failure.
- Pinned dependency audits, backend tests, frontend auth tests, lint/type check and build pass.
- Keyboard/screen-reader and PostgreSQL concurrency/load checks appropriate to expected scale pass before broader launch.
