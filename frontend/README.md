# SmartNest frontend

Next.js app with Supabase sign-in and a Django API. Run `npm ci`, copy `.env.example` to the ignored `.env.local`, configure the API URL, Supabase URL and publishable key, then `npm run dev`. Never expose a secret/service-role key through frontend configuration.

Check with `npm run lint`, `npx tsc --noEmit`, `node --test tests/*.test.cjs` and `npm run build`. Start a built server using `npm run start`. On Windows, if Turbopack cannot use the default temporary folder, set TEMP and TMP to a private writable folder and retry with a fresh build cache.

Account roles come from approved invitations or administrator controls. Admins invite managers; managers invite tenants, staff and providers. Tenant check-in precedes the tenant invitation. Users choose their own passwords and confirm their email. Returning verified tenants can reuse an existing account after their former tenancy is checked out. Privileged accounts require authenticator verification in the API.

Configure production HTTPS Site URL and callback/reset redirect allowlists in Supabase, and verify SMTP delivery. Google, passkeys and phone sign-in depend on provider configuration. The frontend uses Supabase exclusively. Legacy Django passwords are not Supabase credentials.

The public demo uses sample records without registration. Privacy and terms are at `/privacy` and `/terms`; operator legal-name details and ODPC registration remain pending. The public contact is ogonyogad@gmail.com.

Core API requests have a 20-second network timeout plus a 10-second session-lookup deadline. A timed-out mutation may already have saved: refresh/check its result before retrying. Automatic mutation retries are not enabled.

Maintenance uses approval, provider acceptance, tenant coordination and completion confirmation. Inspection automations are optional, with manual controls. Private images are uploaded to access-checked Django storage. Directed notices use server-side encryption, not end-to-end encryption. Mutation metadata is logged without request payloads.

SMS and WhatsApp invitation delivery remain disabled; copying the prepared link is available. The API records payments but does not perform Daraja/bank transactions. See [the production runbook](../docs/PRODUCTION_SECURITY.md) for hosting, backup/supervision, legal release requirements and secure configuration.
