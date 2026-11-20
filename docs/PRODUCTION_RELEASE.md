# Production release and acceptance gate

Status: local preparation only. No host, public domain, SMS provider or live payment service is provisioned.

## Prepare staging
1. Choose the real domain, managed Ubuntu host and managed PostgreSQL region/budget. Keep staging and production data and credentials separate.
2. Review and commit the release files and migrations. Keep private media, .env files, encryption keys and backups outside Git. Historical uploaded photos require a repository-history review before public publication.
3. Create the restricted runtime database role using the supplied SQL example; use separate migration credentials. Copy existing data using backup/restore, never flush the existing database. Compare row counts and upload checksums.
4. Create /etc/smartnest environment files from the examples; configure real HTTPS origins, database CA, private media/static paths and SMTP. Set the frontend public variables before building. Run deploy/validate-production.py with backend, frontend and backup environment paths.
5. Install dependencies, run migrations with the maintenance identity, collectstatic, and run manage.py check --deploy with actual production settings. Run the GitHub release-checks workflow on the final commit.
6. Configure DNS/TLS and Nginx; expose only HTTPS and restricted administration access. Install API/web/worker services, backup/monitor timers and smartnest-alert@.service. Validate unit files with systemd-analyze verify before enabling them. Failure emails require real application SMTP and SMARTNEST_ALERT_EMAIL; test them only with an approved recipient. Also configure an independent external uptime alert, since a stopped server cannot send its own email.
7. Configure scheduled encrypted offsite backups, preserve the separate recovery key, and restore a snapshot into an isolated database/storage directory. Record recovery time and data-loss window. Test service restart and server reboot.

## Authentication and providers
Google and GitHub work locally; repeat on staging using its approved origins and redirect allowlist. Set Supabase Site URL to the deployed frontend. Install all three versioned email templates in deploy/supabase. Test new and existing invite recipients, resend, expiry, duplicate clicks, different devices, password recovery and magic-link code entry. Configure SPF/DKIM/DMARC and check a second inbox provider. Review Supabase email rate limits and leaked-password protection. Keep LinkedIn unavailable until its eligible company Page and OAuth app exist. Review optional administrator MFA enrollment and recovery with the owner; do not silently re-enroll previously disabled accounts.

## Role acceptance matrix
For each admin, manager, staff, maintenance and tenant account, verify sign-in/logout, session expiry, profile, optional MFA, support and permitted private communication. With two different managers, verify cross-manager records and invitation links are denied.

Manager: create property/unit, check in tenant, share invitation via Gmail, accept invitation, find team members, reopen/renew pending staff and maintenance links, assign work, update notices, check expenses and payments. Staff: verify assigned portfolio, tenancy workflows and denied manager-only financial access. Maintenance: verify only assigned work and private photos. Tenant: verify linked home, repair request, payment history and denied foreign records. Admin: verify provisioning and support inbox.

Test uploads through redeployment; confirm unauthorized downloads fail. Test invalid forms, deleted records, missing pages and provider outages without exposing sensitive details. Use phone/tablet widths, keyboard navigation, Chrome/Firefox/Edge/Safari, Lighthouse and moderate concurrent load. Measure authenticated /auth/me latency separately from local SQL timing.

## Optional first-launch services
SMS remains off until provider/sender approval, Kenya delivery, verified phone enrollment, consent/opt-out, retry/reconciliation and spending-alert tests pass. Supabase sign-in SMS and Django property notifications have separate configuration.
Daraja remains sandbox-only. Do not enable live payment claims until business approval, receipt/settlement verification, duplicate-safe ledger posting, audits, refunds/support handling and reconciliation are implemented and tested.

## Cutover and rollback
Take a fresh consistent backup; pause writers during the database transfer. Verify counts/files, migrations, health/readiness, authentication and one complete manager/tenant workflow before reopening writes. Retain the previous release and environment securely. Roll back application code only when database compatibility is confirmed; never restore an old database over newly written production records without a deliberate recovery plan. Record the release commit, operator, timestamps and outcomes. Start with a small pilot before broad invitations.

## Decisions still required
Hosting budget and domain; legal operator/contact details; backup retention and recovery targets; operations alert recipient; SMTP sending domain/provider; whether SMS and M-Pesa are required for launch. No legal identity or service account information should be invented.
