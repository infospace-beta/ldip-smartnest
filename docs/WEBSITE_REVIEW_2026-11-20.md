# SmartNest website and deployment review

Reviewed 20 November 2026 for the SmartNest owner. Source baseline: `ec9a634`. The website works locally and the automated workflow checks pass after the fixes below. It is ready for deployment preparation, but it is not yet a verified online production service.

The agreed hosting budget is **$0**. No paid resources were created and no live deployment was made. Both inspected Vercel and Render workspaces had no deployed SmartNest service. The current Django application stores private uploads on disk; the selected Render architecture needs a paid persistent disk. A complete free deployment therefore needs a storage and hosting adaptation, or an already available persistent host.

## What is implemented

| Area | Current functionality and evidence |
| --- | --- |
| Public website | Homepage, invitation onboarding, sign-in, recovery, confirmation, privacy, terms and interactive demo. Fifteen page routes returned HTTP 200; robots and sitemap also returned 200. The deliberately missing route returned 404. Nine internal link destinations and page fragments had no broken targets in the bounded crawl. |
| Properties and tenancies | Property and unit management, tenant check-in/out, tenancy history, invited account linking and manager ownership. Backend tests cover account and portfolio boundaries. |
| Roles and invitations | Administrator, manager, tenant, staff and maintenance permissions; invitations, acceptance, renewal and team access. Email-service selection, WhatsApp phone routing, SMS drafts and copying links are implemented. These prepare drafts for the user to send. |
| Maintenance | Manager approval, explicit provider assignment, visit coordination, completion reports, resident confirmation and disputed or reopened work. |
| Inspections | Scheduling, resident confirmation or alternative times, inspection reports and optional automation. |
| Financial records | Manual payment records, reconciliation status and expenses. Daraja is sandbox-only and does not settle live rent payments. |
| Communication | Directed notices and permitted private conversations. Property-notification SMS is disabled pending provider setup and acceptance testing. |
| Account security | Supabase identity, password and email-code/link flows, optional authenticator enrollment and backup-email controls. The live capability endpoint reports Google, GitHub, LinkedIn, email and passkeys enabled; phone sign-in is disabled. Enabled configuration is not proof of successful end-to-end provider login. |
| Data persistence | PostgreSQL records and private uploads outside the checkout. No missing referenced uploads were found. A fresh encrypted backup and separate restore rehearsal passed. |

## Fixes completed during this review

- Restarted the stopped automation worker under its existing supervisor. API and worker readiness now pass.
- Took a fresh encrypted snapshot after pausing the local API and worker. Restored it to a separate database and media directory, then restarted the application. All **32 database table counts**, **five uploaded-file checksums**, and the signing key matched; no live database was overwritten.
- Updated compatible development dependencies. The initial npm audit reported seven moderate findings; the update reported **zero vulnerabilities**.
- Removed two unused form definitions. Lint now passes with zero errors and zero warnings.
- Fixed a production-settings test that depended on the current working directory. It now runs from the repository root, matching the CI launch pattern.
- Added an early CI check for unresolved merge markers and made lint warnings fail release checks.
- Corrected outdated invitation-sharing, optional-MFA and deployment documentation.

## Validation results

| Check | Result |
| --- | --- |
| Frontend regressions | **74 passed** after dependency and cleanup changes. |
| Backend regressions | **137 passed on isolated SQLite**; **137 passed again on a uniquely named temporary PostgreSQL database** after fixing the CI path assumption. These are the same backend tests, not 274 distinct tests. |
| TypeScript and production build | Next.js production build passed, including TypeScript and generation of 41 routes. |
| Lint | Zero errors and zero warnings. |
| Source integrity | No unresolved conflict markers; `git diff --check` passed. |
| Database migrations | No model/migration drift detected. |
| Python compatibility | `pip check` passed. `pip-audit` reported no known vulnerabilities across the 16 installed direct and transitive backend runtime packages. |
| Production configuration | Checked in an isolated process with temporary placeholders. HTTPS redirect, secure cookies and DEBUG=false defaults pass. Two optional warnings remain for HSTS subdomains and preload; enable only after verifying the real domain and its subdomains. This does not validate a real host or certificate. |
| Operational health | API/worker ready, media present, recent backup and sufficient disk space: all passed after maintenance. |
| Browser and forms | Chrome desktop review; demo keyboard tab navigation; phone-width checks at 390 px for demo, sign-in, onboarding, privacy, terms, recovery and confirmation. Checked pages had no horizontal overflow. Checked form inputs had accessible labels. Magic-link mode removes the password requirement. |
| Supabase project | Healthy. Security advisor reports leaked-password protection disabled. |

Authenticated browser acceptance for all five real roles, real email delivery, SMS, live payments, Safari/Firefox/Edge, a full screen-reader audit and production load testing remain outside these passing results. No real payment or outgoing invitation message was sent during this review. No Lighthouse score is claimed from local development pages.

## Work required before a public launch

| Priority | Remaining work | Completion condition |
| --- | --- | --- |
| High | Resolve hosting within the $0 budget | Supply an existing host with persistent storage, or adapt private uploads and worker operation to a suitable free-tier architecture. Do not deploy the frontend with a localhost API URL. |
| High | Configure a hosted PostgreSQL target | Provision restricted runtime and migration identities, TLS and a private application schema. Transfer existing records/files with a controlled maintenance window and compare counts/checksums. The current application database is still local. |
| High | Review historical public uploads | Five uploaded-image paths remain in Git history and the repository is public. Removing current files does not remove old versions. Review the images and plan history cleanup with collaborators; no history rewrite was performed. |
| High | Establish offsite recovery and monitoring | The new backup and restore drill are local. Set a recurring encrypted offsite backup process, retention/recovery targets and independent uptime/error alerts. Render disk snapshots alone do not cover the whole database/media recovery procedure. |
| High | Complete staging account acceptance | Verify invitation acceptance, sign-in/logout, confirmation, recovery, magic links and optional MFA for actual roles on the final HTTPS origin. Test cross-manager isolation and private uploads after redeployment. Update Supabase Site URL, redirect allowlist and OAuth origins. |
| Medium | Finalize operational and legal details | Confirm the operator identity, privacy/retention wording, contact and alert recipients, sending domain and SMTP delivery. No legal compliance certification is implied by working pages. |
| Medium | Review leaked-password protection | Supabase's advisor flags it as disabled. The provider documents it as Pro-plan-and-above functionality, so it was not enabled under the $0 instruction. |
| Medium | Verify restart and device behavior | Local background processes are not a Windows startup service. Restart them after a PC reboot. Complete cross-browser, accessibility and realistic production-performance checks on staging. |
| Optional | Activate SMS and live payments | SMS requires provider/sender configuration, consent, delivery and spending controls. Live M-Pesa settlement requires separate implementation, approvals, reconciliation and acceptance testing. They are not prerequisites for a records-only pilot. |

## Deployment preparation

The selected architecture remains Vercel for Next.js and Render for the Django API and one worker. Existing templates are in `deploy/render.yaml.example`, `deploy/render-start.py`, `frontend/.env.production.example` and `backend/.env.production.example`. The operational instructions are in `docs/VERCEL_RENDER.md` and `docs/PRODUCTION_RELEASE.md`.

The inspected Render form quoted $7/month for starter compute and $0.25/GB-month for a disk. A 1 GB pilot disk would make that $7.25/month before database, backups, tax or domain costs. The form was cancelled after the $0 decision; these resources were not purchased. The example Blueprint specifies a paid plan and must not be imported as a zero-cost deployment.

For a later deployment, use repository root build command `pip install -r backend/requirements.txt && python backend/manage.py collectstatic --noinput`, start command `python -B deploy/render-start.py`, readiness path `/api/health/ready/`, and persistent mount `/var/data`. Keep private uploads under `/var/data/media` and the heartbeat under `/var/data/worker/heartbeat`; run migrations with a separate maintenance identity before startup. On Vercel select root directory `frontend`, Node 22, install `npm ci`, and build `npm run build`. Configure real HTTPS API/site origins before building, and preserve authentication and upload access checks.

Secrets and personal uploads must remain in private provider configuration/storage. No secret values are included in this report.

## Provider references

- [Render persistent disk requirements and filesystem behavior](https://render.com/docs/disks).
- [Vercel Next.js deployment documentation](https://vercel.com/docs/frameworks/full-stack/nextjs).
- [Supabase password strength and leaked-password protection](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection).
