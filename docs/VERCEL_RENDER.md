# Vercel frontend and Render backend

This is the selected target architecture. The Ubuntu/systemd runbook remains an alternative, not the primary deployment route.

Vercel: import the repository with Root Directory `frontend`, framework Next.js, Node 22, install `npm ci`, build `npm run build`. Configure the variables in frontend/.env.production.example separately for Preview and Production. NEXT_PUBLIC values are fixed at build time; redeploy after changing them. Use a stable staging domain rather than allowing every Vercel preview hostname in CORS or Supabase redirects.

Render: use deploy/render.yaml.example as a reviewed Blueprint template. It requires a paid web service and persistent disk, plus separately provisioned managed PostgreSQL. Do not use an ephemeral/free filesystem for uploads. API and one automation worker run in the same service under deploy/render-start.py, sharing /var/data for private media and heartbeat. Keep one instance; separate services cannot share the disk. A child exit terminates its sibling and fails the service for Render to restart. Readiness also checks database and worker heartbeat. Disk-based deployment has restart/deploy downtime and is not a horizontally scalable design.

Set production secrets and real frontend/API origins from the environment examples. Configure database TLS and its CA according to the actual database endpoint. Collect static files during build; WhiteNoise serves static assets through Django. Uploaded files remain private and must continue through authorized application endpoints. Never expose /var/data/media as a public static directory.

Before the first start, apply migrations using the separate database maintenance identity from a secure operator environment. The Render start command only checks migrations and refuses to start if pending. Import existing records/files through a controlled migration and compare counts/checksums. Never replace the database with an empty one to make deployment succeed.

Supabase: configure Site URL, redirect allowlist and the Google/GitHub production OAuth origins. Apply the three email templates from deploy/supabase. Test confirmation, recovery and magic links on the Vercel staging domain. Configure the production sending domain, SPF/DKIM/DMARC and provider limits. LinkedIn remains unavailable pending an eligible company Page.

Backups/monitoring: Ubuntu systemd timers do not run on Render. Enable managed PostgreSQL backups appropriate to the chosen plan and independent uptime/error alerts. Persistent disk snapshots alone are not a complete application/database recovery plan. Before public launch, establish encrypted offsite media/database backup scheduling, a consistent capture procedure that pauses API and worker writes, and an isolated restore drill on this architecture. Do not run the Ubuntu systemctl-based backup script on Render. Decide between an operator-controlled maintenance/export procedure for this initial single-instance design and a later private object-storage adaptation with a separate backup service. This is an outstanding launch gate, not completed automation.

Do not place secrets in Vercel NEXT_PUBLIC variables. Review paid service/disk/database costs before creation. No paid resources have been created by these files. Real account connection, region/domain choices, deployment and staging acceptance remain required.
