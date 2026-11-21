# SmartNest pilot operations

SmartNest is operated by Mark Angel. Public support is markangeljr74@gmail.com, available 24/7. Update the shared frontend operator configuration when these details change.

## Retained tenancy history

Move-out changes occupancy and access; it does not delete the tenancy or its check-in/check-out evidence. Django protects tenants, handover events and their related account, home and property records from deletion. PostgreSQL also rejects DELETE and TRUNCATE on the two history tables. These protections apply to the application and its runtime database login; a privileged database owner can still perform explicitly authorized maintenance. There is no automatic record expiry or pruning job. Correction and privacy requests go to the operator and must be reviewed against applicable requirements.

## Hosted records and uploads

Use the private `smartnest` PostgreSQL schema, a migration login for deployments, and the separate application login for runtime. Neither login needs superuser, role-creation or database-creation privileges. Do not expose this schema through the Supabase Data API. Use the IPv4 session pooler with `sslmode=verify-full`. The public certificate in `deploy/supabase/prod-ca-2021.crt` comes from the official Supabase SSL download, not an application secret.

Set `SMARTNEST_MEDIA_BACKEND=s3` and the `SMARTNEST_S3_*` server settings. Keep `smartnest-media` private. Its object keys stay in database records; authorized Django endpoints serve the files. Serializers must never emit direct storage URLs. The Supabase S3 credential bypasses storage policies for every project bucket, so keep it out of client bundles, Git and logs.

To migrate existing uploads, pause writers and run `migrate_private_media --source-root <private-media-directory> --quiesced`. This copies and verifies checksums, preserves keys, refuses differing existing objects, and leaves local files intact. Follow with `check_storage --deployment`.

## Backups and readiness

`cloud_backup` coordinates API and automation writes using PostgreSQL advisory locks, encrypts the database, stored uploads and notice recovery keys, then uploads to a separate private backup bucket. It downloads the encrypted object and compares checksums. `cloud_backup --verify-key <object-key>` additionally decrypts the archive and verifies every member. No snapshot pruning is enabled. Keep the Fernet backup key separately from the bucket; losing it prevents recovery.

The Actions workflow `Cloud backups and readiness` runs the backup at 03:17 Africa/Nairobi and checks readiness twice an hour. Scheduled workflows only run from the repository's default branch. It remains disabled until repository variable `SMARTNEST_OPERATIONS_ENABLED=true` is set. Configure the encrypted repository secret `SMARTNEST_BACKUP_ENV` and variable `SMARTNEST_API_URL` first, then manually dispatch and verify both jobs before relying on the schedule. Use PostgreSQL client 18 for the hosted PostgreSQL 17 database. Backup jobs receive runtime credentials, never migration credentials. No private backup artifact or record dump is uploaded to GitHub Actions artifacts.

Readiness failures fail the Actions job. GitHub notification delivery depends on the operator's workflow notification settings; verify an alert channel separately. A successful archive checksum check does not replace a periodic restore into a separate empty database using `restore_smartnest` and the original notice keys.

## Free hosting

`deploy/render.yaml.example` selects a free API instance, private S3 uploads and an ephemeral worker heartbeat. Database migrations run separately with the migration identity; the service only checks they are current. Do not provision a Render disk or paid database under the $0 budget. Free services sleep when idle, which pauses the worker and delays the first request. Automation catches up on waking; this is a pilot limitation, not an always-on service guarantee.

Deploy the Next.js frontend with its `frontend` root. Only public Supabase configuration and the HTTPS API origin belong in browser environment variables. Configure the actual frontend origin in Django CORS, CSRF and frontend URL settings, and add the deployed authentication callback URLs in Supabase. Never use guessed domains. Review provider free-plan usage before admitting more users. SMTP and live SMS/payment integrations require their own verified configuration.

## Verification boundary

Automated tests cover role permissions, invitations, repairs, inspections, move-out, retention and backup write coordination. Browser checks using one existing staff account do not establish complete real-account acceptance for every role or screen-reader/browser combination. Run the role acceptance checklist on the final deployed origin, using designated pilot accounts and disposable workflow records, before calling the pilot fully accepted.
