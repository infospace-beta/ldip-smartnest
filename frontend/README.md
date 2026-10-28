# SmartNest frontend

The SmartNest frontend is a Next.js app-router application. It connects to the Django REST API and renders property, tenant, payment, maintenance, inspection, notice and staff records from the service.

## Run locally

```bash
npm ci
npm run dev
```

By default, the frontend expects the API at `http://localhost:8000/api`. Set `NEXT_PUBLIC_API_URL` to the deployed API base URL when running or building for another environment. The Django API must allow the frontend origin through CORS.

## Checks

```bash
npm run lint
npm run build
```

Account sign-in and tenant registration use the backend auth endpoints. Property, unit, tenant, payment, expense, maintenance, notice, staff and inspection forms submit to the API endpoints that support those operations. Theme preference is stored in this browser.

SmartNest has four account roles: tenant, staff, maintenance, and manager (who is also the landlord), plus administrator. Public registration is limited to tenant accounts and requires consent. Registration does not sign the tenant in: the manager must link the account to a tenant record before portal access is granted. Administrators provision staff, maintenance, manager, and admin roles from **Users & access**. Staff see only assigned units; tenants see only their own tenancy, payments and maintenance records.

Managers can create staff and maintenance accounts from **Team onboarding** without assigning an apartment. Staff data access can be assigned separately by an administrator. Managers can also add a tenant and generate a one-time, seven-day signup link for the tenant to create and link their portal account; the manager can copy and share the link. Email delivery is not configured.

Managers and assigned staff can record check-in/check-out events. Check-out makes the unit vacant and revokes that tenant's portal access. Maintenance users see only work orders assigned to their account, can submit quotes, and must attach an HTTPS photo URL before marking work complete. Private conversations are restricted to participants; the administrator registry does not expose message text.

The API stores payment records but does not process M-Pesa or bank transactions. SMS delivery, utility balances, landlord remittance/agency-fee calculations, KRA iTax MRI metrics, API gateway configuration, system audit logs and global rate-limit controls are not implemented in the current backend. Completion photos are referenced by HTTPS URL; image upload/storage is not implemented. The current backend has no organization model, so managers operate the portfolio configured in this deployment.
