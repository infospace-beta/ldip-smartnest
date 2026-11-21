"use client";

import {operator} from "@/lib/operator";
import {matchesSearch} from "@/components/RecordFilters";
import AccessibleDialog from "@/components/AccessibleDialog";
import PasswordInput from "@/components/PasswordInput";
import TeamDirectory from "@/components/TeamDirectory";
import AccountInvitationForm from "@/components/AccountInvitationForm";
import InvitationComposer from "@/components/InvitationComposer";
import InvitationShare from "@/components/InvitationShare";
import AdministratorSupport from "@/components/AdministratorSupport";
import ProfilePhotoCropper from "@/components/ProfilePhotoCropper";

import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type FormEvent, type ReactNode } from "react";
import {
  authAPI,
  communicationAPI,
  dashboardAPI,
  expensesAPI,
  getApiErrorMessage,
  healthAPI,
  maintenanceAPI,
  noticesAPI,
  paymentsAPI,
  propertiesAPI,
  staffAPI,
  tenancyEventsAPI,
  tenantsAPI,
  unitInspectionsAPI,
  unitsAPI,
  usersAPI,
  type CommunicationContact,
  type Conversation,
  type DashboardStats,
  type Expense,
  type MaintenanceJob,
  type Notice,
  type Payment,
  type Property,
  type PublicUser,
  type Tenant,
  type TenancyEvent,
  type Unit,
  type UserAccess,
  type UserAssignmentOptions,
} from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import Icon from "@/components/Icon";
import UserAvatar from "@/components/UserAvatar";

type DataRow = Record<string, unknown>;
type References = Record<string, DataRow[]>;
type Option = { label: string; value: string };
type Field = {
  name: string;
  label: string;
  type?: "text" | "email" | "tel" | "number" | "date" | "url" | "select" | "textarea";
  required?: boolean;
  placeholder?: string;
  full?: boolean;
  options?: (references: References) => Option[];
};
type CreateForm = {
  title: string;
  submitLabel: string;
  fields: Field[];
  allowedRoles: string[];
  create: (values: Record<string, string>) => Promise<unknown>;
  afterCreate?: (createdRecord: unknown, values: Record<string, string>) => Promise<string | null>;
  validate?: (values: Record<string, string>) => string | null;
};
type PageConfig = {
  title: string;
  eyebrow: string;
  description: string;
  icon: string;
  columns: { key: string; label: string }[];
  load: () => Promise<{ rows: DataRow[]; references?: References }>;
  forms?: CreateForm[];
  filters?: string[];
};

function rowsOf<T extends object>(items: T[]): DataRow[] {
  return items.map((item) => Object.entries(item).reduce<DataRow>((row, [key, value]) => {
    row[key] = value;
    return row;
  }, {}));
}

function numberValue(values: Record<string, string>, name: string) {
  return Number(values[name] ?? 0);
}

function listOptions(references: References, key: string, labelKey: string): Option[] {
  return (references[key] ?? []).map((item) => ({
    value: String(item.id ?? ""),
    label: String(item[labelKey] ?? "Unnamed"),
  }));
}

function roleDisplayName(role: string) {
  const labels: Record<string, string> = {
    admin: "System administrator",
    manager: "Manager (Landlord)",
    staff: "Agency staff",
    maintenance: "Maintenance",
    tenant: "Tenant",
  };
  return labels[role] ?? role.replaceAll("_", " ");
}

const propertyForm: CreateForm = {
  title: "Add a property",
  submitLabel: "Save property",
  allowedRoles: ["admin", "manager"],
  fields: [
    { name: "name", label: "Property name", required: true, placeholder: "e.g. Greenview Court" },
    { name: "location", label: "Location", required: true, placeholder: "Neighbourhood, city" },
    { name: "cluster", label: "Portfolio / cluster", placeholder: "Nairobi" },
    { name: "total_units", label: "Total units", type: "number", required: true },
    { name: "monthly_rent", label: "Typical monthly rent", placeholder: "KSh 24,000" },
    { name: "tag", label: "Property type", placeholder: "Residential" },
    { name: "photo_url", label: "Photo URL", type: "url", full: true, placeholder: "https://..." },
  ],
  create: (values) => propertiesAPI.create({ ...values, total_units: numberValue(values, "total_units") }),
};

const paymentForm: CreateForm = {
  title: "Record a payment",
  submitLabel: "Save payment",
  allowedRoles: ["admin", "manager"],
  fields: [
    { name: "reference", label: "Payment reference", required: true, placeholder: "M-Pesa or bank reference" },
    { name: "tenant", label: "Tenant", type: "select", required: true, options: (refs) => listOptions(refs, "tenants", "name") },
    { name: "date", label: "Payment date", type: "date", required: true },
    { name: "amount", label: "Amount (KSh)", type: "number", required: true },
    { name: "method", label: "Payment method", type: "select", required: true, options: () => [{ label: "M-Pesa", value: "mpesa" }, { label: "Bank transfer", value: "bank_transfer" }, { label: "Cash", value: "cash" }] },
    { name: "match_status", label: "Match status", type: "select", required: true, options: () => [{ label: "Pending", value: "pending" }, { label: "Matched", value: "matched" }, { label: "Needs review", value: "needs_review" }] },
  ],
  create: (values) => paymentsAPI.create({ ...values, tenant: numberValue(values, "tenant"), amount: numberValue(values, "amount") }),
};

const maintenanceForm: CreateForm = {
  title: "Create a work order",
  submitLabel: "Save work order",
  allowedRoles: ["admin", "manager", "staff"],
  fields: [
    { name: "job_id", label: "Work order ID", required: true, placeholder: "WO-2026-001" },
    { name: "property", label: "Property", type: "select", required: true, options: (refs) => listOptions(refs, "properties", "name") },
    { name: "unit", label: "Unit", type: "select", options: (refs) => listOptions(refs, "units", "unit_number") },
    { name: "issue", label: "Issue", required: true, placeholder: "Describe the repair" },
    { name: "priority", label: "Priority", type: "select", required: true, options: () => [{ label: "Low", value: "low" }, { label: "Medium", value: "medium" }, { label: "High", value: "high" }] },
    { name: "status", label: "Status", type: "select", required: true, options: () => [{ label: "Assigned", value: "assigned" }, { label: "Logged", value: "logged" }, { label: "In progress", value: "in_progress" }, { label: "Completed", value: "completed" }] },
    { name: "reported_by", label: "Reported by", required: true },
    { name: "assignee", label: "Service contact label", required: true },
    { name: "assigned_to", label: "Provider account", type: "select", options: (refs) => [{ label: "Unassigned", value: "" }, ...listOptions(refs, "assignees", "username")] },
    { name: "date", label: "Reported date", type: "date", required: true },
  ],
  create: (values) => maintenanceAPI.create({
    ...values,
    assigned_to: values.assigned_to ? numberValue(values, "assigned_to") : null,
    property: numberValue(values, "property"),
    unit: values.unit ? numberValue(values, "unit") : null,
  }),
};

const tenantMaintenanceForm: CreateForm = {
  title: "Request maintenance",
  submitLabel: "Send request",
  allowedRoles: ["tenant"],
  fields: [
    { name: "issue", label: "What needs attention?", type: "textarea", required: true, full: true, placeholder: "Describe the maintenance issue and where it is in your unit." },
  ],
  create: (values) => maintenanceAPI.create(values),
};

const expenseForm: CreateForm = {
  title: "Record an expense",
  submitLabel: "Save expense",
  allowedRoles: ["admin", "manager"],
  fields: [
    { name: "title", label: "Expense", required: true, placeholder: "Plumbing repair" },
    { name: "category", label: "Category", type: "select", required: true, options: () => ["repairs", "utilities", "maintenance", "insurance", "taxes", "management", "other"].map((item) => ({ label: item[0].toUpperCase() + item.slice(1), value: item })) },
    { name: "amount", label: "Amount (KSh)", type: "number", required: true },
    { name: "property", label: "Property", type: "select", options: (refs) => [{ label: "Unassigned", value: "" }, ...listOptions(refs, "properties", "name")] },
    { name: "date", label: "Expense date", type: "date", required: true },
    { name: "receipt_url", label: "Receipt URL", type: "url", placeholder: "Optional" },
    { name: "description", label: "Notes", type: "textarea", full: true },
  ],
  create: (values) => expensesAPI.create({
    ...values,
    amount: numberValue(values, "amount"),
    property: values.property ? numberValue(values, "property") : null,
  }),
};

const inspectionForm: CreateForm = {
  title: "Add an inspection",
  submitLabel: "Save inspection",
  allowedRoles: ["admin", "manager", "staff"],
  fields: [
    { name: "unit", label: "Unit", type: "select", required: true, options: (refs) => listOptions(refs, "units", "unit_number") },
    { name: "inspector_name", label: "Inspector", required: true },
    { name: "inspection_type", label: "Inspection type", type: "select", required: true, options: () => [{ label: "Routine", value: "routine" }, { label: "Move-in", value: "move_in" }, { label: "Move-out", value: "move_out" }] },
    { name: "inspection_date", label: "Inspection date", type: "date", required: true },
    { name: "condition", label: "Condition", type: "select", required: true, options: () => ["excellent", "good", "fair", "poor"].map((item) => ({ label: item[0].toUpperCase() + item.slice(1), value: item })) },
    ...["doors", "windows", "sink", "washroom", "other"].map((item) => ({ name: `checklist_${item}`, label: `${item[0].toUpperCase()}${item.slice(1)}`, type: "select" as const, options: () => [{ label: "Not checked", value: "not_checked" }, { label: "In good condition", value: "good" }, { label: "Needs attention", value: "needs_attention" }, { label: "Not applicable", value: "not_applicable" }] })),
    { name: "next_inspection_date", label: "Next inspection", type: "date" },
    { name: "issues_found", label: "Issues found", type: "textarea" },
    { name: "recommended_actions", label: "Recommended actions", type: "textarea" },
    { name: "notes", label: "Additional notes", type: "textarea", full: true },
  ],
  create: (values) => {
    const checklist = Object.fromEntries(
      ["doors", "windows", "sink", "washroom", "other"].map((item) => [item, values[`checklist_${item}`] || "not_checked"]),
    );
    return unitInspectionsAPI.create({
      ...values,
      unit: numberValue(values, "unit"),
      checklist,
      next_inspection_date: values.next_inspection_date || null,
    });
  },
};

const noticeForm: CreateForm = {
  title: "Create a notice",
  submitLabel: "Save notice",
  allowedRoles: ["admin", "manager"],
  fields: [
    { name: "title", label: "Title", required: true },
    { name: "state", label: "Delivery state", type: "select", required: true, options: () => [{ label: "Queued", value: "queued" }, { label: "Scheduled", value: "scheduled" }, { label: "Delivered", value: "delivered" }] },
    { name: "icon", label: "Notice category", type: "select", required: true, options: () => ["send", "campaign", "receipt_long", "schedule_send"].map((item) => ({ label: item.replace("_", " "), value: item })) },
    { name: "text", label: "Message", type: "textarea", required: true, full: true },
  ],
  create: (values) => noticesAPI.create(values),
};

const staffForm: CreateForm = {
  title: "Add a team member",
  submitLabel: "Save team member",
  allowedRoles: ["admin"],
  fields: [
    { name: "name", label: "Full name", required: true },
    { name: "email", label: "Email address", type: "email", required: true },
    { name: "role", label: "Team role", required: true },
  ],
  create: (values) => staffAPI.create({
    ...values,
    initials: values.name.split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase() ?? "").join(""),
    roles: [],
  }),
};

const PAGE_CONFIGS: Record<string, PageConfig> = {
  properties: {
    title: "Properties & units", eyebrow: "Portfolio", description: "Keep buildings, unit availability and rent details in one place.", icon: "properties",
    columns: [{ key: "name", label: "Property" }, { key: "location", label: "Location" }, { key: "cluster", label: "Portfolio" }, { key: "total_units", label: "Units" }, { key: "occupied_units", label: "Occupied" }, { key: "status", label: "Status" }],
    load: async () => {
      const [properties, units] = await Promise.all([propertiesAPI.list(), unitsAPI.list()]);
      return { rows: rowsOf(properties.data), references: { properties: rowsOf(properties.data), units: rowsOf(units.data) } };
    },
    forms: [propertyForm],
    filters: ["all", "leased", "vacant"],
  },
  tenants: {
    title: "Tenants & leases", eyebrow: "Portfolio", description: "Review resident records, unit assignments and lease dates.", icon: "tenants",
    columns: [{ key: "name", label: "Tenant" }, { key: "property_name", label: "Property" }, { key: "unit_number", label: "Unit" }, { key: "lease_end", label: "Lease ends" }, { key: "rent", label: "Monthly rent" }, { key: "status", label: "Status" }, { key: "account_linked", label: "Portal account" }],
    load: async () => {
      const [tenants, properties, units] = await Promise.all([tenantsAPI.list(), propertiesAPI.list(), unitsAPI.list()]);
      return { rows: rowsOf(tenants.data), references: { tenants: rowsOf(tenants.data), properties: rowsOf(properties.data), units: rowsOf(units.data) } };
    },
    forms: [],
    filters: ["all", "active", "expiring", "pending"],
  },
  reconciliation: {
    title: "Payments", eyebrow: "Finance", description: "Review payment references and reconciliation status recorded by the service.", icon: "payments",
    columns: [{ key: "reference", label: "Reference" }, { key: "tenant_name", label: "Tenant" }, { key: "date", label: "Date" }, { key: "amount", label: "Amount" }, { key: "method", label: "Method" }, { key: "match_status", label: "Match status" }],
    load: async () => {
      const [payments, tenants] = await Promise.all([paymentsAPI.list(), tenantsAPI.list()]);
      return { rows: rowsOf(payments.data), references: { tenants: rowsOf(tenants.data) } };
    },
    forms: [paymentForm],
    filters: ["all", "matched", "pending", "needs_review"],
  },
  maintenance: {
    title: "Maintenance", eyebrow: "Operations", description: "Track service work orders, priority and resolution status.", icon: "maintenance",
    columns: [{ key: "job_id", label: "Work order" }, { key: "property_name", label: "Property" }, { key: "unit_number", label: "Unit" }, { key: "issue", label: "Issue" }, { key: "reported_by", label: "Reported by" }, { key: "priority", label: "Priority" }, { key: "assignee", label: "Assigned to" }, { key: "status", label: "Status" }, { key: "quote_amount", label: "Quote" }, { key: "confirmation_photo_url", label: "Completion photo" }],
    load: async () => {
      const [jobs, properties, units, assignees] = await Promise.all([maintenanceAPI.list(), propertiesAPI.list(), unitsAPI.list(), maintenanceAPI.assignees()]);
      return { rows: rowsOf(jobs.data), references: { properties: rowsOf(properties.data), units: rowsOf(units.data), assignees: rowsOf(assignees.data) } };
    },
    forms: [maintenanceForm, tenantMaintenanceForm],
    filters: ["all", "assigned", "in_progress", "completed"],
  },
  expenses: {
    title: "Expenses", eyebrow: "Finance", description: "Review property costs and the expense records supplied by the backend.", icon: "expenses",
    columns: [{ key: "title", label: "Expense" }, { key: "category", label: "Category" }, { key: "property_name", label: "Property" }, { key: "amount", label: "Amount" }, { key: "date", label: "Date" }],
    load: async () => {
      const [expenses, properties] = await Promise.all([expensesAPI.list(), propertiesAPI.list()]);
      return { rows: rowsOf(expenses.data), references: { properties: rowsOf(properties.data) } };
    },
    forms: [expenseForm],
  },
  "unit-inspections": {
    title: "Unit inspections", eyebrow: "Operations", description: "Record unit condition, inspection findings and recommended work.", icon: "inspections",
    columns: [{ key: "unit_number", label: "Unit" }, { key: "property_name", label: "Property" }, { key: "inspection_type", label: "Type" }, { key: "inspector_name", label: "Inspector" }, { key: "inspection_date", label: "Date" }, { key: "condition", label: "Condition" }, { key: "checklist", label: "Checklist" }, { key: "issues_found", label: "Findings" }],
    load: async () => {
      const [inspections, units] = await Promise.all([unitInspectionsAPI.list(), unitsAPI.list()]);
      return { rows: rowsOf(inspections.data), references: { units: rowsOf(units.data) } };
    },
    forms: [inspectionForm],
    filters: ["all", "excellent", "good", "fair", "poor"],
  },
  notices: {
    title: "Notices", eyebrow: "Communications", description: "Review announcements and messages recorded in the workspace.", icon: "notices",
    columns: [{ key: "title", label: "Notice" }, { key: "text", label: "Message" }, { key: "state", label: "State" }, { key: "created_at", label: "Created" }],
    load: async () => ({ rows: rowsOf((await noticesAPI.list()).data) }),
    forms: [noticeForm],
    filters: ["all", "queued", "scheduled", "delivered"],
  },
  staff: {
    title: "Staff & roles", eyebrow: "Administration", description: "View the team directory and the role details provided by the service.", icon: "staff",
    columns: [{ key: "name", label: "Team member" }, { key: "role", label: "Role" }, { key: "email", label: "Email" }, { key: "roles", label: "Access" }],
    load: async () => ({ rows: rowsOf((await staffAPI.list()).data) }),
    forms: [staffForm],
  },
};

function displayValue(value: unknown, key?: string) {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (typeof value === "boolean" && key === "account_linked") return value ? "Linked" : "Not linked";
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .filter(([, item]) => item !== "" && item !== null && item !== undefined)
      .map(([itemKey, item]) => `${itemKey.replaceAll("_", " ")}: ${String(item).replaceAll("_", " ")}`)
      .join(" · ") || "—";
  }
  if (["date", "lease_end", "created_at", "inspection_date"].includes(key ?? "") && typeof value === "string") {
    const date = new Date(value);
    if (!Number.isNaN(date.getTime())) return date.toLocaleDateString();
  }
  if (["amount", "quote_amount"].includes(key ?? "") && (typeof value === "number" || (typeof value === "string" && value.trim() !== ""))) {
    const amount = Number(value);
    if (Number.isFinite(amount)) return `KSh ${amount.toLocaleString()}`;
  }
  if (typeof value === "number" && Number.isFinite(value)) return value.toLocaleString();
  return String(value);
}

function statusClass(key: string, value: unknown) {
  if (!["status", "match_status", "priority", "condition", "state"].includes(key)) return "";
  const status = String(value).toLowerCase();
  if (["active", "matched", "completed", "delivered", "excellent", "occupied", "leased"].includes(status)) return "green";
  if (["high", "needs_review", "expiring", "fair", "in_progress", "pending_approval"].includes(status)) return "warning";
  if (["poor", "rejected"].includes(status)) return "danger";
  return "";
}

function PageHeader({ title, eyebrow, description, icon, actions }: { title: string; eyebrow: string; description: string; icon: string; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <div className="page-eyebrow"><Icon name={icon} />{eyebrow}</div>
        <h1 className="page-title">{title}</h1>
        <p className="page-description">{description}</p>
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

function PublicProfileDialog({
  userId,
  name,
  hasAvatar,
  onClose,
}: {
  userId: number;
  name: string;
  hasAvatar?: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const { user } = useAuth();
  const [profile, setProfile] = useState<PublicUser | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    usersAPI.profile(userId)
      .then(({ data }) => { if (active) setProfile(data); })
      .catch(() => { if (active) setError("This profile could not be loaded or is outside your access scope."); });
    return () => { active = false; };
  }, [userId]);

  return (
    <div className="profile-overlay" role="presentation" onClick={onClose}>
      <AccessibleDialog onClose={onClose} className="panel tenant-profile-dialog public-profile-dialog" aria-modal="true" aria-labelledby="public-profile-title" onClick={(event) => event.stopPropagation()}>
        <button className="button button-secondary button-compact tenant-profile-close" type="button" onClick={onClose}>Close</button>
        <div className="tenant-profile-heading">
          <UserAvatar userId={userId} hasAvatar={profile?.has_avatar ?? hasAvatar} name={profile?.username ?? name} className="profile-avatar" />
          <div>
            <div className="page-eyebrow">Contact profile</div>
            <h2 id="public-profile-title">{profile?.username ?? name}</h2>
            <p>{roleDisplayName(profile?.role ?? "tenant")}</p>
          </div>
        </div>
        {error ? <div className="error-state" role="alert">{error}</div> : !profile ? (
          <div className="loading-state" role="status">Loading profile...</div>
        ) : (
          <dl className="tenant-profile-details">
            <div><dt>Phone</dt><dd>{profile.phone ? <a href={`tel:${profile.phone}`}>{profile.phone}</a> : "Not provided"}</dd></div>
            <div><dt>Role</dt><dd>{roleDisplayName(profile.role)}</dd></div>
            {profile.property_cluster && <div><dt>Portfolio</dt><dd>{profile.property_cluster}</dd></div>}
          </dl>
        )}
        {profile && profile.id !== user?.id && (
          <div className="form-actions tenant-profile-actions">
            <button className="button button-primary" type="button" onClick={() => router.push(`/dashboard/messages?recipient=${userId}`)}><Icon name="notices" />Message</button>
          </div>
        )}
        <p className="panel-description">Only the contact details this person shares for property operations are shown here.</p>
      </AccessibleDialog>
    </div>
  );
}

function RecordForm({ form, references, onSaved }: { form: CreateForm; references: References; onSaved: () => Promise<void> }) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [inviteLink, setInviteLink] = useState("");
  const [inviteError, setInviteError] = useState("");
  const [inviteRecipient, setInviteRecipient] = useState({email:"",name:"there"});
  const [selectedProperty, setSelectedProperty] = useState("");
  const [selectedUnit, setSelectedUnit] = useState("");

  if (!user || !form.allowedRoles.includes(user.role)) return null;
  if (user.role === "tenant" && form.title === "Request maintenance" && (!(references.properties ?? []).length || !(references.units ?? []).length)) {
    return <div className="hint-card"><strong>Tenant record not linked</strong>Your manager needs to link your account to a tenant and unit record before you can submit a maintenance request.</div>;
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    const formData = new FormData(event.currentTarget);
    const values = Object.fromEntries([...formData.entries()].map(([key, value]) => [key, String(value)]));
    const validationError = form.validate?.(values);
    if (validationError) {
      setError(validationError);
      setSaving(false);
      return;
    }
    try {
      const createdRecord = await form.create(values);
      setOpen(false);
      if (form.afterCreate && values.invite_email?.trim()) {
        try {
          setInviteLink(await form.afterCreate(createdRecord, values) ?? "");
          setInviteError("");
          setInviteRecipient({email:values.invite_email||"",name:values.name||"there"});
        } catch {
          setInviteLink("");
          setInviteError("Tenant saved, but the invite link could not be created. Check the email and try again from the tenant record.");
        }
      }
      await onSaved();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "The record could not be saved. Check the fields and try again."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <button className={open ? "button button-secondary button-compact" : "button button-primary"} type="button" onClick={() => { setOpen((value) => !value); setError(""); }}>
        <Icon name={open ? "close" : "add"} />{open ? "Close" : form.title}
      </button>
      {inviteLink && (
        <div className="hint-card invite-link-card" role="status">
          <strong>Tenant invite link ready</strong>
          <span>Share this one-time link with the tenant. It expires in 7 days.</span>
          <InvitationShare link={inviteLink} email={inviteRecipient.email} name={inviteRecipient.name}/>
        </div>
      )}
      {inviteError && <div className="error-state" role="alert">{inviteError}</div>}
      {open && (
        <section className="panel form-panel">
          <div className="panel-heading"><div><h2 className="panel-title">{form.title}</h2><p className="panel-description">This record is saved through the SmartNest API.</p></div></div>
          <form onSubmit={handleSubmit}>
            <div className="form-grid">
              {form.fields.map((field) => (
                <div className={`field ${field.full ? "field-full" : ""}`} key={field.name}>
                  <label htmlFor={`${form.title}-${field.name}`}>{field.label}</label>
                  {field.type === "textarea" ? (
                    <textarea id={`${form.title}-${field.name}`} name={field.name} required={field.required} placeholder={field.placeholder} />
                  ) : field.type === "select" ? (
                    <select
                      id={`${form.title}-${field.name}`}
                      name={field.name}
                      required={field.required}
                      defaultValue={field.name === "unit" ? undefined : ""}
                      value={field.name === "unit" ? selectedUnit : undefined}
                      onChange={field.name === "property" ? (event) => {
                        setSelectedProperty(event.target.value);
                        setSelectedUnit("");
                      } : field.name === "unit" ? (event) => setSelectedUnit(event.target.value) : undefined}
                    >
                      <option value="" disabled>Select {field.label.toLowerCase()}</option>
                      {(field.name === "unit" && selectedProperty
                        ? (references.units ?? []).filter((unit) => String(unit.property) === selectedProperty).map((unit) => ({ value: String(unit.id), label: String(unit.unit_number ?? "Unit") }))
                        : field.options?.(references) ?? []).map((option) => <option value={option.value} key={`${option.value}-${option.label}`}>{option.label}</option>)}
                    </select>
                  ) : (
                    <input id={`${form.title}-${field.name}`} name={field.name} type={field.type ?? "text"} required={field.required} placeholder={field.placeholder} min={field.type === "number" ? "0" : undefined} step={field.type === "number" ? (field.name === "total_units" ? "1" : "0.01") : undefined} />
                  )}
                </div>
              ))}
            </div>
            {error && <div className="form-error" role="alert">{error}</div>}
            <div className="form-actions">
              <button className="button button-secondary button-compact" type="button" onClick={() => setOpen(false)}>Close</button>
              <button className="button button-primary" type="submit" disabled={saving}>{saving ? "Saving..." : form.submitLabel}</button>
            </div>
          </form>
        </section>
      )}
    </>
  );
}

function VendorWorkOrderForm({
  jobId,
  status,
  quoteAmount,
  quoteNotes,
  confirmationPhotoUrl,
  onSaved,
}: {
  jobId: number;
  status: string;
  quoteAmount: number | null;
  quoteNotes: string;
  confirmationPhotoUrl: string;
  onSaved: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const nextStatus = status === "in_progress" ? "completed" : "in_progress";

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSaving(true);
    setError("");
    try {
      const amount = String(form.get("quote_amount") ?? "").trim();
      await maintenanceAPI.update(jobId, {
        status: String(form.get("status") ?? nextStatus),
        quote_amount: amount ? Number(amount) : null,
        quote_notes: String(form.get("quote_notes") ?? ""),
        confirmation_photo_url: String(form.get("confirmation_photo_url") ?? ""),
      });
      setOpen(false);
      await onSaved();
    } catch {
      setError("Could not save your work-order update. A completion photo is required to mark a job complete.");
    } finally {
      setSaving(false);
    }
  };

  if (status === "completed") return <span className="panel-description">Complete</span>;
  return (
    <div className="vendor-update">
      <button className="button button-secondary" type="button" onClick={() => setOpen((value) => !value)}>{open ? "Close" : "Update"}</button>
      {open && <form className="vendor-update-form" onSubmit={submit}>
        <label className="field"><span>Work status</span><select name="status" defaultValue={nextStatus}><option value={nextStatus}>{nextStatus.replaceAll("_", " ")}</option></select></label>
        <label className="field"><span>Quote amount (KSh)</span><input name="quote_amount" type="number" min="0.01" step="0.01" defaultValue={quoteAmount ?? ""} /></label>
        <label className="field"><span>Quote details</span><textarea name="quote_notes" rows={2} defaultValue={quoteNotes} /></label>
        <label className="field"><span>Completion photo URL</span><input name="confirmation_photo_url" type="url" defaultValue={confirmationPhotoUrl} placeholder="Required to complete work" /></label>
        {error && <span className="form-error" role="alert">{error}</span>}
        <button className="button button-primary" type="submit" disabled={saving}>{saving ? "Saving..." : "Save update"}</button>
      </form>}
    </div>
  );
}

function MaintenancePhotoButton({ jobId, label = "View damage photo" }: { jobId: number; label?: string }) {
  const [photoUrl, setPhotoUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => () => {
    if (photoUrl) URL.revokeObjectURL(photoUrl);
  }, [photoUrl]);

  const openPhoto = async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await maintenanceAPI.photo(jobId);
      setPhotoUrl(URL.createObjectURL(data));
    } catch {
      setError("This photo could not be loaded.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <button className="button button-secondary button-compact" type="button" onClick={() => void openPhoto()} disabled={loading}>
        <Icon name="inspections" />{loading ? "Loading..." : label}
      </button>
      {error && <span className="form-error" role="alert">{error}</span>}
      {photoUrl && (
        <div className="evidence-overlay" role="presentation" onClick={() => setPhotoUrl("")}>
          <AccessibleDialog onClose={() => setPhotoUrl("")} className="evidence-dialog" aria-label="Maintenance damage photo" onClick={(event) => event.stopPropagation()}>
            <button className="button button-secondary" type="button" onClick={() => setPhotoUrl("")}>Close photo</button>
            <Image src={photoUrl} alt="Reported maintenance damage" width={1200} height={900} unoptimized />
          </AccessibleDialog>
        </div>
      )}
    </>
  );
}

function MaintenanceRequestPanel({ onSaved }: { onSaved: () => Promise<void> }) {
  const [issue, setIssue] = useState("");
  const [priority, setPriority] = useState("medium");
  const [photo, setPhoto] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  const choosePhoto = (file: File | null) => {
    setError("");
    if (file && file.size > 5 * 1024 * 1024) {
      setError("Choose a photo that is 5 MB or smaller.");
      setPhoto(null);
      setPreview("");
      return;
    }
    setPhoto(file);
    setPreview(file ? URL.createObjectURL(file) : "");
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      await maintenanceAPI.request({
        issue: issue.trim(),
        priority,
        damage_photo_upload: photo ?? undefined,
      });
      setIssue("");
      setPriority("medium");
      choosePhoto(null);
      setSuccess("Request sent. Your manager will review it and assign the right service team.");
      await onSaved();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Your maintenance request could not be sent."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="panel form-panel">
      <div className="panel-heading">
        <div>
          <h2 className="panel-title">Request a repair</h2>
          <p className="panel-description">Tell your manager what needs attention, choose how urgent it is, and attach a photo so the damage can be assessed before approval.</p>
        </div>
      </div>
      <form onSubmit={submit}>
        <div className="form-grid">
          <div className="field field-full">
            <label htmlFor="maintenance-issue">What needs attention?</label>
            <textarea id="maintenance-issue" required maxLength={200} value={issue} onChange={(event) => setIssue(event.target.value)} placeholder="Describe the issue and where it is in your unit." />
          </div>
          <div className="field">
            <label htmlFor="maintenance-priority">How urgent is it?</label>
            <select id="maintenance-priority" value={priority} onChange={(event) => setPriority(event.target.value)}>
              <option value="low">Low — can wait for a scheduled visit</option>
              <option value="medium">Medium — needs attention soon</option>
              <option value="high">High — urgent or unsafe</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="maintenance-photo">Damage photo (optional)</label>
            <input id="maintenance-photo" type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => choosePhoto(event.target.files?.[0] ?? null)} />
            <span className="field-hint">JPEG, PNG or WebP, up to 5 MB. This helps the manager and service team assess the work.</span>
          </div>
          {preview && <div className="field field-full"><Image className="maintenance-photo-preview" src={preview} alt="Damage photo preview" width={640} height={420} unoptimized /></div>}
        </div>
        {error && <div className="form-error" role="alert">{error}</div>}
        {success && <div className="hint-card" role="status"><strong>Request submitted</strong>{success}</div>}
        <div className="form-actions">
          <button className="button button-primary" type="submit" disabled={saving || !issue.trim()}>
            <Icon name="arrow" />{saving ? "Sending..." : "Send request for approval"}
          </button>
        </div>
      </form>
    </section>
  );
}

function MaintenanceApprovalCard({
  job,
  assignees,
  onSaved,
  onViewProfile,
}: {
  job: MaintenanceJob;
  assignees: CommunicationContact[];
  onSaved: () => Promise<void>;
  onViewProfile: (userId: number, name: string, hasAvatar?: boolean) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const approve = async () => {
    setSaving(true);
    setError("");
    try {
      await maintenanceAPI.approve(job.id, {});
      await onSaved();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "This request could not be approved."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <article className="panel maintenance-approval-card">
      <div className="maintenance-card-head">
        <div>
          <div className="page-eyebrow"><Icon name="maintenance" />Awaiting your approval</div>
          <h3>{job.issue}</h3>
          <p className="panel-description">{job.job_id} · {new Date(job.date).toLocaleDateString()} · {job.property_name}{job.unit_number ? ` · Unit ${job.unit_number}` : ""}</p>
        </div>
        <div className="maintenance-badges">
          <span className={`status-pill ${statusClass("priority", job.priority)}`}>{job.priority} priority</span>
          {job.has_damage_photo && <MaintenancePhotoButton jobId={job.id} />}
        </div>
      </div>
      <div className="maintenance-requester">
        <UserAvatar userId={job.reported_by_user_id ?? undefined} hasAvatar={job.reported_by_has_avatar} name={job.reported_by} className="user-avatar" />
        <div><strong>{job.reported_by}</strong><small>Tenant request</small></div>
        {job.reported_by_user_id && <button className="profile-trigger" type="button" onClick={() => onViewProfile(job.reported_by_user_id!, job.reported_by, job.reported_by_has_avatar)}>View profile</button>}
      </div>
      {!assignees.length && <p className="field-hint">No service account is linked yet. The request can be approved and the manager can arrange a service contact later.</p>}
      {error && <div className="form-error" role="alert">{error}</div>}
      <div className="form-actions">
        <button className="button button-primary" type="button" onClick={() => void approve()} disabled={saving}><Icon name="check" />{saving ? "Approving..." : "Approve request"}</button>
      </div>
    </article>
  );
}

function TenantMaintenanceHistory({ jobs, onViewProfile }: { jobs: MaintenanceJob[]; onViewProfile: (userId: number, name: string, hasAvatar?: boolean) => void }) {
  if (!jobs.length) {
    return <div className="empty-state"><strong>No maintenance requests yet</strong>When something in your unit needs attention, send a request above and it will appear here.</div>;
  }
  return (
    <div className="maintenance-job-list">
      {jobs.map((job) => (
        <article className="panel maintenance-job-card" key={job.id}>
          <div className="maintenance-card-head">
            <div>
              <div className="maintenance-badges">
                <span className={`status-pill ${statusClass("status", job.status)}`}>{job.status.replaceAll("_", " ")}</span>
                <span className={`status-pill ${statusClass("priority", job.priority)}`}>{job.priority} priority</span>
              </div>
              <h3>{job.issue}</h3>
              <p className="panel-description">{job.job_id} · {new Date(job.date).toLocaleDateString()} · {job.property_name}{job.unit_number ? ` · Unit ${job.unit_number}` : ""}</p>
            </div>
            {job.has_damage_photo && <MaintenancePhotoButton jobId={job.id} />}
          </div>
          {job.status === "pending_approval" && <p className="hint-card"><strong>Waiting for approval</strong>Your manager is reviewing this request. You will be able to contact the service team once it is approved.</p>}
          {job.status === "rejected" && <p className="hint-card"><strong>Request declined</strong>{job.manager_notes || "Contact your manager if you need more information about this decision."}</p>}
          {job.manager_notes && job.status !== "rejected" && <p className="panel-description"><strong>Manager note:</strong> {job.manager_notes}</p>}
          {(job.assigned_to_name || job.status === "assigned" || job.status === "in_progress" || job.status === "completed") && (
            <div className="maintenance-service-row">
              <UserAvatar userId={job.assigned_to ?? undefined} hasAvatar={job.assigned_to_has_avatar} name={job.assigned_to_name || job.assignee} className="user-avatar" />
              <div><strong>{job.assigned_to_name || job.assignee}</strong><small>Service team{job.approved_by_name ? ` · approved by ${job.approved_by_name}` : ""}</small></div>
              {job.assigned_to && <button className="profile-trigger" type="button" onClick={() => onViewProfile(job.assigned_to!, job.assigned_to_name || job.assignee, job.assigned_to_has_avatar)}>View profile</button>}
              {job.assigned_to && <Link className="button button-primary button-compact" href={`/dashboard/messages?recipient=${job.assigned_to}`}><Icon name="message" />Message service</Link>}
            </div>
          )}
          {job.status !== "pending_approval" && job.status !== "rejected" && !job.assigned_to && <p className="field-hint">Approved. Your manager is arranging the service team.</p>}
          {job.quote_notes && <p className="panel-description"><strong>Service update:</strong> {job.quote_notes}</p>}
        </article>
      ))}
    </div>
  );
}

function ServiceMaintenanceHistory({ jobs, onSaved, onViewProfile }: { jobs: MaintenanceJob[]; onSaved: () => Promise<void>; onViewProfile: (userId: number, name: string, hasAvatar?: boolean) => void }) {
  if (!jobs.length) {
    return <div className="empty-state"><strong>No approved work orders yet</strong>Requests assigned to you by a manager will appear here after approval.</div>;
  }
  return (
    <div className="maintenance-job-list">
      {jobs.map((job) => (
        <article className="panel maintenance-job-card" key={job.id}>
          <div className="maintenance-card-head">
            <div>
              <div className="maintenance-badges">
                <span className={`status-pill ${statusClass("status", job.status)}`}>{job.status.replaceAll("_", " ")}</span>
                <span className={`status-pill ${statusClass("priority", job.priority)}`}>{job.priority} priority</span>
              </div>
              <h3>{job.issue}</h3>
              <p className="panel-description">{job.job_id} · {new Date(job.date).toLocaleDateString()} · {job.property_name}{job.unit_number ? ` · Unit ${job.unit_number}` : ""}</p>
            </div>
            {job.has_damage_photo && <MaintenancePhotoButton jobId={job.id} />}
          </div>
          <div className="maintenance-service-row">
            <UserAvatar userId={job.reported_by_user_id ?? undefined} hasAvatar={job.reported_by_has_avatar} name={job.reported_by} className="user-avatar" />
            <div><strong>{job.reported_by}</strong><small>Tenant who reported the issue</small></div>
            {job.reported_by_user_id && <button className="profile-trigger" type="button" onClick={() => onViewProfile(job.reported_by_user_id!, job.reported_by, job.reported_by_has_avatar)}>View profile</button>}
            {job.reported_by_user_id && <Link className="button button-secondary button-compact" href={`/dashboard/messages?recipient=${job.reported_by_user_id}`}><Icon name="message" />Message tenant</Link>}
          </div>
          {job.manager_notes && <p className="panel-description"><strong>Manager note:</strong> {job.manager_notes}</p>}
          <div className="maintenance-service-actions">
            <VendorWorkOrderForm jobId={job.id} status={job.status} quoteAmount={typeof job.quote_amount === "number" ? job.quote_amount : null} quoteNotes={job.quote_notes} confirmationPhotoUrl={job.confirmation_photo_url} onSaved={onSaved} />
          </div>
        </article>
      ))}
    </div>
  );
}

function MaintenanceAssignment({ job, assignees, onSaved }: {
  job: MaintenanceJob;
  assignees: CommunicationContact[];
  onSaved: () => Promise<void>;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const account = String(new FormData(event.currentTarget).get("provider") ?? "");
    setSaving(true);
    setError("");
    try {
      await maintenanceAPI.update(job.id, {
        assigned_to: account ? Number(account) : null,
        ...(account && job.status === "logged" ? { status: "assigned" } : {}),
      });
      await onSaved();
    } catch (failure) {
      setError(getApiErrorMessage(failure, "The provider could not be assigned."));
    } finally {
      setSaving(false);
    }
  };
  return (
    <form onSubmit={save}>
      <select name="provider" aria-label={`Provider for ${job.job_id}`} defaultValue={job.assigned_to ?? ""}>
        <option value="">Unassigned</option>
        {assignees.map((provider) => <option key={provider.id} value={provider.id}>{provider.username}</option>)}
      </select>
      <button className="button button-secondary button-compact" type="submit" disabled={saving}>{saving ? "Saving..." : "Save provider"}</button>
      {error && <p role="alert">{error}</p>}
    </form>
  );
}

export function MaintenancePage() {
  const { user } = useAuth();
  const role = user?.role ?? "";
  const isManagerial = role === "manager" || role === "staff";
  const [jobs, setJobs] = useState<MaintenanceJob[]>([]);
  const [assignees, setAssignees] = useState<CommunicationContact[]>([]);
  const [properties, setProperties] = useState<Property[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedProfile, setSelectedProfile] = useState<{ userId: number; name: string; hasAvatar?: boolean } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const jobResponse = await maintenanceAPI.list();
      setJobs(jobResponse.data);
      if (isManagerial) {
        const [propertyResponse, unitResponse, assigneeResponse] = await Promise.all([
          propertiesAPI.list(),
          unitsAPI.list(),
          maintenanceAPI.assignees(),
        ]);
        setProperties(propertyResponse.data);
        setUnits(unitResponse.data);
        setAssignees(assigneeResponse.data);
      }
    } catch {
      setError("Maintenance requests could not be loaded from the SmartNest API.");
    } finally {
      setLoading(false);
    }
  }, [isManagerial]);

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      if (active) void load();
    });
    return () => { active = false; };
  }, [load]);

  const orderedJobs = useMemo(() => [...jobs].sort((left, right) => {
    const rank = (status: string) => status === "pending_approval" ? 0 : status === "rejected" ? 3 : 1;
    return rank(left.status) - rank(right.status) || right.id - left.id;
  }), [jobs]);
  const pendingJobs = orderedJobs.filter((job) => job.status === "pending_approval");
  const openJobs = jobs.filter((job) => ["assigned", "in_progress", "logged"].includes(job.status));
  const completedJobs = jobs.filter((job) => job.status === "completed");
  const highPriorityJobs = jobs.filter((job) => job.priority === "high" && job.status !== "completed" && job.status !== "rejected");
  const references: References = { properties: rowsOf(properties), units: rowsOf(units), assignees: rowsOf(assignees) };
  const viewProfile = (userId: number, name: string, hasAvatar?: boolean) => setSelectedProfile({ userId, name, hasAvatar });
  const description = role === "tenant"
    ? "Report an issue, choose how urgent it is, and follow your manager's approval and the service team's progress."
    : role === "maintenance"
      ? "Review approved work orders assigned to you and keep the tenant updated as the repair progresses."
      : "Approve tenant requests, assign the right service team, and keep every repair moving.";

  return (
    <section>
      <PageHeader
        title="Maintenance"
        eyebrow={role === "tenant" ? "Your repair requests" : role === "maintenance" ? "Service work orders" : "Approvals & work orders"}
        description={description}
        icon="maintenance"
        actions={isManagerial ? <RecordForm form={maintenanceForm} references={references} onSaved={load} /> : undefined}
      />
      {error && <div className="error-state" role="alert"><span>{error}</span><button className="button button-secondary" type="button" onClick={() => void load()}>Try again</button></div>}
      {loading ? <div className="loading-state" role="status">Loading maintenance requests...</div> : !error && (
        <>
          <div className="metric-grid">
            <Metric label={role === "tenant" ? "Your requests" : "Pending approval"} value={role === "tenant" ? jobs.length : pendingJobs.length} note={role === "tenant" ? "Submitted by your account" : "Tenant requests waiting for you"} icon="maintenance" />
            <Metric label="Open work orders" value={openJobs.length} note="Approved and still in progress" icon="inspections" />
            <Metric label="Completed" value={completedJobs.length} note="Repairs marked complete" icon="check" />
            <Metric label="High priority" value={highPriorityJobs.length} note="Urgent open requests" icon="notices" />
          </div>

          {role === "tenant" && <MaintenanceRequestPanel onSaved={load} />}

          {isManagerial && (
            <section className="maintenance-approval-section">
              <div className="panel-heading">
                <div><h2 className="panel-title">Requests awaiting approval</h2><p className="panel-description">Approve the request and assign a service team member. That is all that is needed to start the repair conversation.</p></div>
              </div>
              {pendingJobs.length ? (
                <div className="maintenance-approval-list">
                  {pendingJobs.map((job) => <MaintenanceApprovalCard job={job} assignees={assignees} onSaved={load} onViewProfile={viewProfile} key={job.id} />)}
                </div>
              ) : <div className="empty-state"><strong>No requests waiting</strong>New tenant maintenance requests will appear here for approval.</div>}
            </section>
          )}

          {role === "tenant" ? <TenantMaintenanceHistory jobs={orderedJobs} onViewProfile={viewProfile} /> : role === "maintenance" ? <ServiceMaintenanceHistory jobs={orderedJobs} onSaved={load} onViewProfile={viewProfile} /> : (
            <section className="panel">
              <div className="panel-heading"><div><h2 className="panel-title">All maintenance records</h2><p className="panel-description">{orderedJobs.length} work order{orderedJobs.length === 1 ? "" : "s"} in your portfolio.</p></div></div>
              {orderedJobs.length ? (
                <div className="table-wrap">
                  <table>
                    <thead><tr><th>Work order</th><th>Issue</th><th>Tenant</th><th>Property / unit</th><th>Priority</th><th>Status</th><th>Service team</th><th>Photo</th></tr></thead>
                    <tbody>
                      {orderedJobs.map((job) => (
                        <tr key={job.id}>
                          <td className="table-primary">{job.job_id}<br /><small>{new Date(job.date).toLocaleDateString()}</small></td>
                          <td>{job.issue}</td>
                          <td>
                            <span className="conversation-person">
                              <UserAvatar userId={job.reported_by_user_id ?? undefined} hasAvatar={job.reported_by_has_avatar} name={job.reported_by} className="user-avatar" />
                              {job.reported_by_user_id ? <button className="table-primary profile-trigger" type="button" onClick={() => viewProfile(job.reported_by_user_id!, job.reported_by, job.reported_by_has_avatar)}>{job.reported_by}</button> : job.reported_by}
                            </span>
                            {job.reported_by_user_id && <Link className="button button-secondary button-compact" href={`/dashboard/messages?recipient=${job.reported_by_user_id}`}><Icon name="message" />Message</Link>}
                          </td>
                          <td>{job.property_name}{job.unit_number ? ` · ${job.unit_number}` : ""}</td>
                          <td><span className={`status-pill ${statusClass("priority", job.priority)}`}>{job.priority}</span></td>
                          <td><span className={`status-pill ${statusClass("status", job.status)}`}>{job.status.replaceAll("_", " ")}</span></td>
                          <td>
                            {job.assigned_to_name || job.assignee}
                            {job.assigned_to && <button className="profile-trigger" type="button" onClick={() => viewProfile(job.assigned_to!, job.assigned_to_name || job.assignee, job.assigned_to_has_avatar)}>View profile</button>}
                            {job.status !== "pending_approval" && job.status !== "rejected" && <MaintenanceAssignment key={`${job.id}-${job.assigned_to}`} job={job} assignees={assignees} onSaved={load} />}
                          </td>
                          <td>{job.has_damage_photo ? <MaintenancePhotoButton jobId={job.id} label="View" /> : <span className="panel-description">None</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <div className="empty-state"><strong>No work orders yet</strong>Tenant requests and work orders will appear here.</div>}
            </section>
          )}
        </>
      )}
      {selectedProfile && (
        <PublicProfileDialog
          userId={selectedProfile.userId}
          name={selectedProfile.name}
          hasAvatar={selectedProfile.hasAvatar}
          onClose={() => setSelectedProfile(null)}
        />
      )}
    </section>
  );
}

export function RecordsPage({ page }: { page: string }) {
  const config = PAGE_CONFIGS[page];
  const { user } = useAuth();
  const router = useRouter();
  const userRole = user?.role;
  const [rows, setRows] = useState<DataRow[]>([]);
  const [references, setReferences] = useState<References>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [selectedTenant, setSelectedTenant] = useState<DataRow | null>(null);
  const [selectedProfile, setSelectedProfile] = useState<{ userId: number; name: string; hasAvatar?: boolean } | null>(null);
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = page === "maintenance" && userRole === "maintenance"
        ? { rows: rowsOf((await maintenanceAPI.list()).data) }
        : await config.load();
      setRows(data.rows);
      setReferences(data.references ?? {});
    } catch (requestError) {
      setError(getApiErrorMessage(requestError,"Could not load these records. Please try again."));
    } finally {
      setLoading(false);
    }
  }, [config, page, userRole]);

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      if (active) void load();
    });
    return () => { active = false; };
  }, [load]);

  const filteredRows = useMemo(() => rows.filter((row) => {
    const matchesText = matchesSearch(Object.values(row), search);
    const status = String(row.status ?? row.match_status ?? row.condition ?? row.state ?? "").toLowerCase();
    return matchesText && (filter === "all" || status === filter);
  }), [filter, rows, search]);

  const canWrite = Boolean(config.forms?.some((form) => user && form.allowedRoles.includes(user.role)));
  const actions = config.forms?.filter((form) => user && form.allowedRoles.includes(user.role)).map((form) => (
    <RecordForm form={form} references={references} onSaved={load} key={form.title} />
  ));

  return (
    <section>
      <PageHeader title={config.title} eyebrow={config.eyebrow} description={config.description} icon={config.icon} actions={page === "tenants" && user?.role === "manager" ? <Link className="button button-primary" href="/dashboard/properties">Add tenant through a vacant house</Link> : actions} />
      {config.filters && (
        <div className="filter-tabs" role="group" aria-label="Filter records">
          {config.filters.map((item) => (
            <button type="button" className={`filter-tab ${filter === item ? "active" : ""}`} key={item} onClick={() => setFilter(item)}>
              {item === "all" ? "All records" : item.replaceAll("_", " ")}
            </button>
          ))}
        </div>
      )}
      <section className="panel">
        <div className="toolbar">
          <div><h2 className="panel-title">{config.title} directory</h2><p className="panel-description">{rows.length} record{rows.length === 1 ? "" : "s"} returned by the backend.</p></div>
          <label className="search-field"><Icon name="search" /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={`Search ${config.title.toLowerCase()}...`} aria-label={`Search ${config.title}`} /></label>
        </div>
        <p role="status" className="flow-caption">{filteredRows.length} of {rows.length} records</p>
        {(search||filter!=="all")&&<button type="button" className="button button-secondary button-compact" onClick={()=>{setSearch("");setFilter("all");}}>Clear search and filters</button>}
        {error && <div className="error-state" role="alert"><span>{error}</span><button className="button button-secondary" type="button" onClick={() => void load()}>Try again</button></div>}
        {loading ? <div className="loading-state" role="status">Loading records...</div> : !error && filteredRows.length === 0 ? (
          <div className="empty-state"><strong>{rows.length ? "No matching records" : "Nothing here yet"}</strong>{rows.length ? "Try changing the search or filter." : canWrite ? "Add a record to get this workspace started." : "Records will appear here when the service has data."}</div>
        ) : !error ? (
          <div className="table-wrap">
            <table>
              <thead><tr>{config.columns.map((column) => <th key={column.key}>{column.label}</th>)}{page === "maintenance" && user?.role === "maintenance" && <th>Action</th>}</tr></thead>
              <tbody>
                {filteredRows.map((row, index) => (
                  <tr key={String(row.id ?? row.reference ?? row.job_id ?? index)}>
                    {config.columns.map((column, cellIndex) => {
                      const value = row[column.key];
                      const formatted = displayValue(value, column.key);
                      const className = statusClass(column.key, value);
                      const photoUrl = column.key === "confirmation_photo_url" && typeof value === "string" && value.startsWith("https://") ? value : null;
                      return <td key={column.key}>{photoUrl ? <a href={photoUrl} target="_blank" rel="noreferrer">View photo</a> : page === "tenants" && column.key === "name" ? (
                        <span className="conversation-person">
                          <UserAvatar
                            userId={typeof row.account_user_id === "number" ? row.account_user_id : undefined}
                            hasAvatar={Boolean(row.account_has_avatar)}
                            name={formatted}
                            className="user-avatar"
                          />
                          <button className="table-primary tenant-profile-trigger" type="button" onClick={() => {
                            setSelectedTenant(row);
                          }}>{formatted}</button>
                        </span>
                      ) : page === "maintenance" && column.key === "reported_by" && typeof row.reported_by_user_id === "number" ? (
                        <button className="table-primary profile-trigger" type="button" onClick={() => setSelectedProfile({
                          userId: Number(row.reported_by_user_id),
                          name: formatted,
                          hasAvatar: Boolean(row.reported_by_has_avatar),
                        })}>{formatted}</button>
                      ) : className ? <span className={`status-pill ${className}`}>{formatted.replaceAll("_", " ")}</span> : <span className={cellIndex === 0 ? "table-primary" : ""}>{formatted}</span>}</td>;
                    })}
                    {page === "maintenance" && user?.role === "maintenance" && typeof row.id === "number" && <td><VendorWorkOrderForm jobId={row.id} status={String(row.status ?? "logged")} quoteAmount={typeof row.quote_amount === "number" ? row.quote_amount : null} quoteNotes={String(row.quote_notes ?? "")} confirmationPhotoUrl={String(row.confirmation_photo_url ?? "")} onSaved={load} /></td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {page === "properties" && !loading && !error && (
          <section style={{ marginTop: 22 }}>
            <div className="panel-heading"><div><h2 className="panel-title">Unit directory</h2><p className="panel-description">{(references.units ?? []).length} units returned by the unit service.</p></div></div>
            {(references.units ?? []).length ? (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Unit</th><th>Property</th><th>Type</th><th>Rent</th><th>Status</th><th>Tenant</th></tr></thead>
                  <tbody>{(references.units ?? []).map((unit, index) => <tr key={String(unit.id ?? index)}><td className="table-primary">{displayValue(unit.unit_number)}</td><td>{displayValue(unit.property_name)}</td><td>{displayValue(unit.unit_type)}</td><td>{displayValue(unit.rent)}</td><td><span className={`status-pill ${statusClass("status", unit.status)}`}>{displayValue(unit.status)}</span></td><td>{displayValue(unit.tenant)}</td></tr>)}</tbody>
                </table>
              </div>
            ) : <div className="empty-state"><strong>No units yet</strong>Add units to a property to see them here.</div>}
          </section>
        )}
      </section>
      {page === "tenants" && selectedTenant && (
        <div className="profile-overlay" role="presentation" onClick={() => setSelectedTenant(null)}>
          <AccessibleDialog onClose={() => setSelectedTenant(null)} className="panel tenant-profile-dialog" aria-modal="true" aria-labelledby="tenant-profile-title" onClick={(event) => event.stopPropagation()}>
            <button className="button button-secondary button-compact tenant-profile-close" type="button" onClick={() => setSelectedTenant(null)}>Close</button>
            <div className="tenant-profile-heading">
              <UserAvatar
                userId={typeof selectedTenant.account_user_id === "number" ? selectedTenant.account_user_id : undefined}
                hasAvatar={Boolean(selectedTenant.account_has_avatar)}
                name={String(selectedTenant.name ?? "Tenant")}
                className="profile-avatar"
              />
              <div><div className="page-eyebrow">Tenant profile</div><h2 id="tenant-profile-title">{String(selectedTenant.name ?? "Tenant")}</h2><p>{String(selectedTenant.property_name ?? "Property")} · {String(selectedTenant.unit_number ?? "No unit assigned")}</p></div>
            </div>
            <dl className="tenant-profile-details">
              <div><dt>Phone</dt><dd>{String(selectedTenant.phone ?? "—")}</dd></div>
              <div><dt>Lease status</dt><dd>{String(selectedTenant.status ?? "—").replaceAll("_", " ")}</dd></div>
              <div><dt>Lease ends</dt><dd>{displayValue(selectedTenant.lease_end, "lease_end")}</dd></div>
              <div><dt>Monthly rent</dt><dd>{displayValue(selectedTenant.rent, "rent")}</dd></div>
              <div><dt>Portal account</dt><dd>{selectedTenant.account_linked ? "Linked" : "Not linked"}</dd></div>
            </dl>
            {typeof selectedTenant.account_user_id === "number" && (
              <div className="form-actions tenant-profile-actions">
                <button className="button button-primary" type="button" onClick={() => router.push(`/dashboard/messages?recipient=${selectedTenant.account_user_id}`)}>Message tenant</button>
                <button className="button button-secondary" type="button" onClick={() => setSelectedProfile({
                  userId: Number(selectedTenant.account_user_id),
                  name: String(selectedTenant.name ?? "Tenant"),
                  hasAvatar: Boolean(selectedTenant.account_has_avatar),
                })}>View contact profile</button>
              </div>
            )}
            {!selectedTenant.account_linked && user && ["manager", "staff"].includes(user.role) && (
              <div className="tenant-invitation-panel">
                <h3>Share an account invitation</h3>
                {selectedTenant.can_invite ? <InvitationComposer key={String(selectedTenant.id)} name={String(selectedTenant.name)} defaultEmail={String(selectedTenant.invitation_email ?? "")} defaultPhone={String(selectedTenant.phone ?? "")} prepare={async (email) => {
                  const { data } = await tenantsAPI.invite(Number(selectedTenant.id), email);
                  const url = new URL("/join", window.location.origin);
                  url.searchParams.set("token", data.token);
                  return url.toString();
                }} /> : <p className="panel-description">Complete this tenant’s check-in before preparing their registration invitation.</p>}
              </div>
            )}
          </AccessibleDialog>
        </div>
      )}
      {selectedProfile && (
        <PublicProfileDialog
          userId={selectedProfile.userId}
          name={selectedProfile.name}
          hasAvatar={selectedProfile.hasAvatar}
          onClose={() => setSelectedProfile(null)}
        />
      )}
    </section>
  );
}

function UserAccessRow({
  user,
  options,
  onSaved,
}: {
  user: UserAccess;
  options: UserAssignmentOptions;
  onSaved: () => Promise<void>;
}) {
  const { user: currentUser } = useAuth();
  const isCurrentUser = currentUser?.id === user.id;
  const [role, setRole] = useState(user.role);
  const [active, setActive] = useState(user.is_active_user);
  const [assignedUnits, setAssignedUnits] = useState(user.assigned_units.map(String));
  const [managedProperties, setManagedProperties] = useState(user.managed_property_ids.map(String));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await usersAPI.update(user.id, {
        role,
        is_active_user: active,
        assigned_units: ["staff", "maintenance"].includes(role) ? assignedUnits.map(Number) : [],
        managed_properties: role === "manager" ? managedProperties.map(Number) : [],
      });
      await onSaved();
    } catch {
      setError("Could not save this user’s access. Check the assignments and try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="user-access-row" onSubmit={save}>
      <div className="user-access-identity">
        <strong>{user.username}</strong>
        <span>{user.email}</span>
        {user.role === "tenant" && <small>{user.portal_access_granted ? "Tenant portal enabled" : "Waiting for manager to link tenant record"}</small>}
      </div>
      <label className="access-field">
        <span>Role</span>
        <select value={role} disabled={isCurrentUser} onChange={(event) => setRole(event.target.value)}>
          {["tenant", "staff", "maintenance", "manager", "admin"].map((item) => (
            <option value={item} key={item}>{roleDisplayName(item)}</option>
          ))}
        </select>
      </label>
      {["staff", "maintenance"].includes(role) && (
        <label className="access-field access-assignment">
          <span>Assigned units</span>
          <select multiple value={assignedUnits} onChange={(event) => setAssignedUnits(Array.from(event.currentTarget.selectedOptions, (option) => option.value))}>
            {options.units.map((unit) => <option value={String(unit.id)} key={unit.id}>{unit.property_name} · {unit.unit_number}</option>)}
          </select>
        </label>
      )}
      {role === "manager" && (
        <label className="access-field access-assignment">
          <span>Properties this manager owns</span>
          <select multiple value={managedProperties} onChange={(event) => setManagedProperties(Array.from(event.currentTarget.selectedOptions, (option) => option.value))}>
            {options.properties.map((property) => <option value={String(property.id)} key={property.id}>{property.name}{property.owner_id && property.owner_id !== user.id ? " · reassigned" : ""}</option>)}
          </select>
        </label>
      )}
      <label className="access-active">
        <input type="checkbox" checked={active} disabled={isCurrentUser} onChange={(event) => setActive(event.target.checked)} />
        Active
      </label>
      <div className="access-save">
        <button className="button button-primary" type="submit" disabled={saving}>{saving ? "Saving..." : "Save access"}</button>
        {error && <span className="form-error" role="alert">{error}</span>}
      </div>
    </form>
  );
}

export function UserAccessPage() {
  const [users, setUsers] = useState<UserAccess[]>([]);
  const [options, setOptions] = useState<UserAssignmentOptions>({ properties: [], units: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [usersResponse, optionsResponse] = await Promise.all([
        usersAPI.list(),
        usersAPI.assignmentOptions(),
      ]);
      setUsers(usersResponse.data);
      setOptions(optionsResponse.data);
    } catch {
      setError("Could not load the user registry. Only an administrator can manage user access.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      if (active) void load();
    });
    return () => { active = false; };
  }, [load]);

  return (
    <section>
      <PageHeader
        title="Users & access"
        eyebrow="System administration"
        description="Grant and revoke tenant, staff, maintenance, manager (landlord), and admin access."
        icon="staff"
      />
      <AccountInvitationForm manager />
      <div className="hint-card"><strong>Provisioning flow</strong>Users create tenant accounts from the sign-in page. A manager links tenant accounts to records; administrators grant staff, maintenance, manager (landlord), and admin roles here.</div>
      <div className="hint-card"><strong>Staff access</strong>Staff inherit the portfolio of the manager who onboarded them. Assigning units here adds a direct override for staff who were created before manager onboarding, while maintenance accounts only need work-order assignments.</div>
      <div className="hint-card"><strong>Property ownership</strong>Assign each managed property to its manager here. Managers only see records connected to their assigned properties; unassigned legacy properties remain visible to administrators until assigned.</div>
      {error && <div className="error-state" role="alert"><span>{error}</span><button className="button button-secondary" type="button" onClick={() => void load()}>Try again</button></div>}
      {loading ? <div className="loading-state" role="status">Loading user registry...</div> : !error && (
        <section className="panel user-access-panel">
          <div className="panel-heading">
            <div><h2 className="panel-title">Registered accounts</h2><p className="panel-description">{users.length} account{users.length === 1 ? "" : "s"} · private conversations are not shown in this registry.</p></div>
          </div>
          {users.length ? users.map((item) => <UserAccessRow user={item} options={options} onSaved={load} key={item.id} />) : <div className="empty-state"><strong>No accounts yet</strong>New sign-ups will appear here for role provisioning.</div>}
        </section>
      )}
    </section>
  );
}

export function TeamOnboardingPage() {
  return <TeamDirectory/>;
}

export function CommunicationsPage() {
  const { user } = useAuth();
  const [contacts, setContacts] = useState<CommunicationContact[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [messages, setMessages] = useState<Awaited<ReturnType<typeof communicationAPI.messages>>["data"]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [newConversation, setNewConversation] = useState(false);
  const [selectedRecipient, setSelectedRecipient] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [selectedProfile, setSelectedProfile] = useState<{ userId: number; name: string; hasAvatar?: boolean } | null>(null);

  const loadInbox = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [contactResponse, conversationResponse] = await Promise.all([
        communicationAPI.contacts(),
        communicationAPI.conversations(),
      ]);
      setContacts(contactResponse.data);
      setConversations(conversationResponse.data);
      setSelectedId((current) => current && conversationResponse.data.some((item) => item.id === current)
        ? current
        : conversationResponse.data[0]?.id ?? null);
    } catch {
      setError("Could not load your conversations. Check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      if (active) void loadInbox();
    });
    return () => { active = false; };
  }, [loadInbox]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const recipient = new URLSearchParams(window.location.search).get("recipient");
      if (recipient && /^\d+$/.test(recipient)) {
        setSelectedRecipient(recipient);
        setNewConversation(true);
        setSelectedId(null);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!selectedId) {
      return;
    }
    let active = true;
    communicationAPI.messages(selectedId)
      .then(({ data }) => { if (active) setMessages(data); })
      .catch(() => { if (active) setError("This conversation could not be loaded."); });
    return () => { active = false; };
  }, [selectedId]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const body = String(data.get("body") ?? "");
    setSending(true);
    setError("");
    try {
      if (newConversation) {
        const result = await communicationAPI.startConversation({
          recipient: Number(data.get("recipient")),
          subject: String(data.get("subject") ?? "").trim(),
          body,
        });
        setConversations((current) => [result.data, ...current]);
        setSelectedId(result.data.id);
        setNewConversation(false);
        setSelectedRecipient("");
      } else if (selectedId) {
        await communicationAPI.sendMessage(selectedId, body);
        const { data: updatedMessages } = await communicationAPI.messages(selectedId);
        setMessages(updatedMessages);
        await loadInbox();
      }
      form.reset();
    } catch {
      setError("Your message could not be sent. Please try again.");
    } finally {
      setSending(false);
    }
  };

  const selected = conversations.find((item) => item.id === selectedId);
  const recipientName = selected?.participants.find((participant) => participant.id !== user?.id)?.username;

  return (
    <section>
      <PageHeader
        title="Communications"
        eyebrow="Private messages"
        description="Message the people connected to your role and assignments. Only conversation participants can read its messages."
        icon="notices"
        actions={<button className="button button-primary" type="button" onClick={() => { setNewConversation(true); setSelectedId(null); setSelectedRecipient(""); setMessages([]); }}><Icon name="add" />New message</button>}
      />
      {error && <div className="error-state" role="alert">{error}</div>}
      <div className="communication-grid">
        <aside className="panel conversation-list">
          <h2 className="panel-title">Inbox</h2>
          {loading ? <div className="loading-state" role="status">Loading...</div> : conversations.length ? conversations.map((item) => {
            const participant = item.participants.find((entry) => entry.id !== user?.id);
            return (
              <div className="conversation-item" key={item.id}>
                <button type="button" className={`conversation-link ${!newConversation && selectedId === item.id ? "active" : ""}`} onClick={() => { setNewConversation(false); setSelectedId(item.id); }}>
                  <span className="conversation-person"><UserAvatar userId={participant?.id} hasAvatar={participant?.has_avatar} name={participant?.username ?? "Conversation"} className="user-avatar" /><strong>{participant?.username ?? "Conversation"}</strong></span>
                  <span>{item.subject}</span>
                  <small>{item.last_message_preview}</small>
                </button>
                {participant && <button className="profile-trigger conversation-profile-link" type="button" onClick={() => setSelectedProfile({ userId: participant.id, name: participant.username, hasAvatar: participant.has_avatar })}>View {participant.username}’s profile</button>}
              </div>
            );
          }) : <p className="panel-description">No conversations yet. Start a message with someone available to your role.</p>}
        </aside>
        <section className="panel conversation-thread">
          {newConversation ? (
            <>
              <h2 className="panel-title">New message</h2>
              {contacts.length ? (
                <form className="message-form" onSubmit={submit}>
                  <label className="field"><span>To</span><select name="recipient" required value={selectedRecipient} onChange={(event) => setSelectedRecipient(event.target.value)}><option value="" disabled>Select a contact</option>{contacts.map((contact) => <option key={contact.id} value={contact.id}>{contact.username} · {roleDisplayName(contact.role)}</option>)}</select></label>
                  <label className="field"><span>Subject</span><input name="subject" required maxLength={200} /></label>
                  <label className="field"><span>Message</span><textarea name="body" required rows={5} /></label>
                  <button className="button button-primary" type="submit" disabled={sending}>{sending ? "Sending..." : "Send message"}</button>
                </form>
              ) : <div className="empty-state"><strong>No contacts available</strong>Your role and property assignments determine who you can message.</div>}
            </>
          ) : selected ? (
            <>
              <div className="conversation-heading"><div className="conversation-person">{(() => {
                const participant = selected.participants.find((entry) => entry.id !== user?.id);
                return <UserAvatar userId={participant?.id} hasAvatar={participant?.has_avatar} name={participant?.username ?? recipientName ?? selected.subject} className="user-avatar" />;
              })()}<div><h2 className="panel-title">{(() => {
                const participant = selected.participants.find((entry) => entry.id !== user?.id);
                return participant ? <button className="profile-trigger panel-title-trigger" type="button" onClick={() => setSelectedProfile({ userId: participant.id, name: participant.username, hasAvatar: participant.has_avatar })}>{participant.username}</button> : recipientName ?? selected.subject;
              })()}</h2><p className="panel-description">{selected.subject}</p></div></div></div>
              <div className="message-list" aria-live="polite">
                {messages.map((message) => {
                  const sender = message.sender === user?.id
                    ? user
                    : contacts.find((contact) => contact.id === message.sender);
                  return <article className={`message-bubble ${message.sender === user?.id ? "mine" : ""}`} key={message.id}><span className="conversation-person"><UserAvatar userId={sender?.id} hasAvatar={sender?.has_avatar} name={message.sender_name} className="user-avatar" />{sender ? <button className="profile-trigger" type="button" onClick={() => setSelectedProfile({ userId: sender.id, name: message.sender_name, hasAvatar: sender.has_avatar })}>{message.sender_name}</button> : <strong>{message.sender_name}</strong>}</span><p>{message.body}</p><small>{new Date(message.sent_at).toLocaleString()}</small></article>;
                })}
              </div>
              <form className="message-reply" onSubmit={submit}><label className="field"><span>Reply</span><textarea name="body" rows={3} required /></label><button className="button button-primary" type="submit" disabled={sending}>{sending ? "Sending..." : "Send reply"}</button></form>
            </>
          ) : <div className="empty-state"><strong>Choose a conversation</strong>Your messages stay private to the participants.</div>}
        </section>
      </div>
      <p className="privacy-note">Administrators can provision roles, but cannot browse conversations they are not part of.</p>
      {selectedProfile && (
        <PublicProfileDialog
          userId={selectedProfile.userId}
          name={selectedProfile.name}
          hasAvatar={selectedProfile.hasAvatar}
          onClose={() => setSelectedProfile(null)}
        />
      )}
    </section>
  );
}

export function TenancyEventsPage() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [units, setUnits] = useState<Awaited<ReturnType<typeof unitsAPI.list>>["data"]>([]);
  const [events, setEvents] = useState<TenancyEvent[]>([]);
  const [selectedTenant, setSelectedTenant] = useState("");
  const [action, setAction] = useState<"check_in" | "check_out">("check_in");
  const [notes, setNotes] = useState("");
  const [evidenceFile, setEvidenceFile] = useState<File | null>(null);
  const [evidencePreview, setEvidencePreview] = useState("");
  const [viewingEvidence, setViewingEvidence] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [selectedProfile, setSelectedProfile] = useState<{ userId: number; name: string; hasAvatar?: boolean } | null>(null);

  useEffect(() => () => {
    if (evidencePreview) URL.revokeObjectURL(evidencePreview);
  }, [evidencePreview]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [tenantResponse, eventResponse, unitResponse] = await Promise.all([
        tenantsAPI.list(),
        tenancyEventsAPI.list(),
        unitsAPI.list(),
      ]);
      setTenants(tenantResponse.data);
      setEvents(eventResponse.data);
      setUnits(unitResponse.data);
      setSelectedTenant((current) => current || String(tenantResponse.data[0]?.id ?? ""));
    } catch {
      setError("Could not load tenancy records. Check your assigned units and try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      if (active) void load();
    });
    return () => { active = false; };
  }, [load]);

  const tenant = tenants.find((item) => String(item.id) === selectedTenant);
  const unitStatus = units.find((item) => item.id === tenant?.unit)?.status;
  const canCheckIn = Boolean(tenant?.unit && tenant.status === "pending" && unitStatus === "vacant");
  const canCheckOut = Boolean(tenant?.unit && ["active", "expiring"].includes(tenant.status) && unitStatus === "occupied");
  const actionAvailable = action === "check_in" ? canCheckIn : canCheckOut;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!tenant?.unit) return;
    if (evidenceFile && evidenceFile.size > 5 * 1024 * 1024) {
      setError("Photos must be 5 MB or smaller.");
      return;
    }
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      await tenancyEventsAPI.create({
        tenant: tenant.id,
        unit: tenant.unit,
        action,
        notes,
        ...(evidenceFile ? { evidence_upload: evidenceFile } : {}),
      });
      setSuccess(action === "check_in" ? "Tenant checked in. Portal access remains controlled by the manager." : "Tenant checked out and their portal access is revoked.");
      setNotes("");
      setEvidenceFile(null);
      const photoInput = document.getElementById("handover-photo") as HTMLInputElement | null;
      if (photoInput) photoInput.value = "";
      await load();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "The tenancy event could not be saved."));
    } finally {
      setSaving(false);
    }
  };

  const openEvidence = async (eventId: number) => {
    try {
      const { data } = await tenancyEventsAPI.photo(eventId);
      setViewingEvidence(URL.createObjectURL(data));
    } catch {
      setError("Could not load this photo. Check your access and try again.");
    }
  };

  const closeEvidence = () => {
    if (viewingEvidence) URL.revokeObjectURL(viewingEvidence);
    setViewingEvidence("");
  };

  return (
    <section>
      <PageHeader title="Check-in & check-out" eyebrow="Move workflow" description="Managers and assigned staff record a move-in or move-out against the tenant’s assigned unit." icon="calendar" />
      {error && <div className="error-state" role="alert">{error}</div>}
      {success && <div className="auth-message success" role="status">{success}</div>}
      <section className="panel">
        <div className="panel-heading"><div><h2 className="panel-title">Record a tenancy event</h2><p className="panel-description">Check-in marks the unit occupied. A manager grants tenant portal access by linking the tenant account; check-out makes the unit vacant and revokes that access.</p></div></div>
        {loading ? <div className="loading-state" role="status">Loading assigned tenants...</div> : tenants.length ? (
          <form onSubmit={submit}>
            <div className="form-grid">
              <label className="field"><span>Tenant</span><select value={selectedTenant} onChange={(event) => setSelectedTenant(event.target.value)} required><option value="" disabled>Select tenant</option>{tenants.map((item) => <option value={item.id} key={item.id}>{item.name} · {item.property_name} {item.unit_number ? `· ${item.unit_number}` : ""}</option>)}</select></label>
              <label className="field"><span>Action</span><select value={action} onChange={(event) => setAction(event.target.value as "check_in" | "check_out")}><option value="check_in">Check in</option><option value="check_out">Check out</option></select></label>
              <label className="field field-full"><span>Notes</span><textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={3} placeholder="Optional handover notes" /></label>
              <label className="field field-full">
                <span>Handover photo (optional)</span>
                <input
                  id="handover-photo"
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  capture="environment"
                  onChange={(event) => {
                    const selected = event.currentTarget.files?.[0] ?? null;
                    if (selected && !["image/jpeg", "image/png", "image/webp"].includes(selected.type)) {
                      setError("Choose a JPEG, PNG, or WebP photo.");
                      event.currentTarget.value = "";
                      setEvidenceFile(null);
                      return;
                    }
                    setEvidenceFile(selected);
                    setEvidencePreview(selected ? URL.createObjectURL(selected) : "");
                    setError("");
                  }}
                />
                <small className="field-hint">Take a photo with your phone camera or choose an image. Maximum 5 MB.</small>
                {evidencePreview && <Image className="handover-photo-preview" src={evidencePreview} alt="Selected handover evidence preview" width={720} height={520} unoptimized />}
              </label>
            </div>
            {tenant && !tenant.unit && <div className="hint-card"><strong>No unit assigned</strong>Assign this tenant to a unit before recording a move.</div>}
            {tenant?.unit && !actionAvailable && <div className="hint-card"><strong>Action unavailable</strong>{action === "check_in" ? "Check-in requires a pending tenancy and a vacant unit." : "Check-out requires an active tenancy and an occupied unit."}</div>}
            <div className="form-actions"><button className="button button-primary" type="submit" disabled={saving || !actionAvailable}>{saving ? "Saving..." : action === "check_in" ? "Record check-in" : "Record check-out"}</button></div>
          </form>
        ) : <div className="empty-state"><strong>No assigned tenants</strong>Tenants with an assigned unit will appear here.</div>}
      </section>
      <section className="panel tenancy-events-panel">
        <div className="panel-heading"><div><h2 className="panel-title">Recent move events</h2><p className="panel-description">Check-in and check-out audit history for your access scope.</p></div></div>
        {events.length ? <div className="table-wrap"><table><thead><tr><th>Action</th><th>Tenant</th><th>Property & unit</th><th>Recorded by</th><th>Date</th><th>Evidence</th><th>Notes</th></tr></thead><tbody>{events.map((item) => <tr key={item.id}><td><span className={`status-pill ${item.action === "check_in" ? "green" : ""}`}>{item.action.replaceAll("_", " ")}</span></td><td><span className="conversation-person">{item.tenant_user_id ? <UserAvatar userId={item.tenant_user_id} hasAvatar={item.tenant_has_avatar} name={item.tenant_name} className="user-avatar" /> : null}{item.tenant_user_id ? <button className="table-primary profile-trigger" type="button" onClick={() => setSelectedProfile({ userId: item.tenant_user_id as number, name: item.tenant_name, hasAvatar: item.tenant_has_avatar })}>{item.tenant_name}</button> : item.tenant_name}</span></td><td>{item.property_name} · {item.unit_number}</td><td>{item.recorded_by_name}</td><td>{new Date(item.recorded_at).toLocaleString()}</td><td>{item.evidence_photo ? <button className="button button-secondary button-compact" type="button" onClick={() => void openEvidence(item.id)}>View photo</button> : "—"}</td><td>{item.notes || "—"}</td></tr>)}</tbody></table></div> : <div className="empty-state"><strong>No move events yet</strong>Recorded check-ins and check-outs will be listed here.</div>}
      </section>
      {viewingEvidence && <div className="evidence-overlay" role="presentation" onClick={closeEvidence}><AccessibleDialog onClose={closeEvidence} className="evidence-dialog" aria-label="Handover evidence photo" onClick={(event) => event.stopPropagation()}><button className="button button-secondary" type="button" onClick={closeEvidence}>Close photo</button><Image src={viewingEvidence} alt="Handover evidence" width={1200} height={900} unoptimized /></AccessibleDialog></div>}
      {selectedProfile && (
        <PublicProfileDialog
          userId={selectedProfile.userId}
          name={selectedProfile.name}
          hasAvatar={selectedProfile.hasAvatar}
          onClose={() => setSelectedProfile(null)}
        />
      )}
    </section>
  );
}

function metricValue(value: number | string | undefined) {
  return value === undefined ? "—" : value;
}

function Metric({ label, value, note, icon }: { label: string; value: number | string; note: string; icon: string }) {
  return <article className="metric-card"><div className="metric-head"><span className="metric-label">{label}</span><span className="metric-icon"><Icon name={icon} /></span></div><div className="metric-value">{value}</div><div className="metric-note">{note}</div></article>;
}

export function OverviewPage() {
  const { user } = useAuth();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [jobs, setJobs] = useState<MaintenanceJob[]>([]);
  const [tenantProfile, setTenantProfile] = useState<Tenant | null>(null);
  const [adminUsers, setAdminUsers] = useState<UserAccess[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const role = user?.role ?? "";

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      if (role === "tenant") {
        setStats(null);
        const [tenantResponse, paymentResponse, jobResponse] = await Promise.all([
          tenantsAPI.list(),
          paymentsAPI.list(),
          maintenanceAPI.list(),
        ]);
        setTenantProfile(tenantResponse.data[0] ?? null);
        setPayments(paymentResponse.data);
        setJobs(jobResponse.data);
      } else if (role === "maintenance") {
        const jobResponse = await maintenanceAPI.list();
        setStats(null);
        setPayments([]);
        setJobs(jobResponse.data);
      } else if (role === "staff") {
        const [statsResponse, jobResponse] = await Promise.all([
          dashboardAPI.stats(),
          maintenanceAPI.list(),
        ]);
        setStats(statsResponse.data);
        setPayments([]);
        setJobs(jobResponse.data);
      } else if (role === "admin") {
        const userResponse = await usersAPI.list();
        setStats(null);
        setPayments([]);
        setJobs([]);
        setAdminUsers(userResponse.data);
      } else {
        const [statsResponse, paymentResponse, jobResponse] = await Promise.all([
          dashboardAPI.stats(),
          paymentsAPI.list(),
          maintenanceAPI.list(),
        ]);
        setStats(statsResponse.data);
        setPayments(paymentResponse.data);
        setJobs(jobResponse.data);
      }
    } catch (requestError) {
      setError(getApiErrorMessage(requestError,"Some workspace information could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, [role]);

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      if (active) void load();
    });
    return () => { active = false; };
  }, [load]);

  const occupancy = stats ? stats.occupied_units + stats.vacant_units : 0;
  const occupancyRate = occupancy ? Math.round((stats!.occupied_units / occupancy) * 100) : 0;
  const recentPayments = payments.slice(0, 5);
  const roleTitle = role === "tenant" ? "Your SmartNest account" : role === "maintenance" ? "Service overview" : role === "manager" ? "Manager overview" : role === "admin" ? "System administration" : "Agency staff workspace";

  if (role === "tenant") {
    return (
      <section>
        <PageHeader title={roleTitle} eyebrow="Your home" description={`Welcome, ${user?.username || user?.email}. Your workspace is ready.`} icon="home" />
        {error && <div className="error-state" role="alert"><span>{error}</span><button className="button button-secondary" onClick={() => void load()} type="button">Try again</button></div>}
        {!error && loading ? <div className="loading-state" role="status">Loading your account...</div> : !error && (
          <>
            <div className="metric-grid">
              <Metric label="Monthly rent" value={tenantProfile?.rent ?? "—"} note={tenantProfile?.unit_number ? `${tenantProfile.unit_number} · ${tenantProfile.property_name}` : "Your tenancy record"} icon="home" />
              <Metric label="Lease status" value={tenantProfile?.status ?? "Not linked"} note={tenantProfile?.lease_end ? `Ends ${new Date(tenantProfile.lease_end).toLocaleDateString()}` : "Ask your manager to link your lease"} icon="calendar" />
              <Metric label="Payments" value={payments.length} note="Records linked to your account" icon="payments" />
              <Metric label="Maintenance requests" value={jobs.length} note="Requests linked to your account" icon="maintenance" />
            </div>
            <div className="dashboard-grid">
              <section className="panel">
                <div className="panel-heading"><div><h2 className="panel-title">Recent rent payments</h2><p className="panel-description">Payment records linked to your tenant profile.</p></div><Link className="button button-secondary" href="/dashboard/reconciliation">View payments <Icon name="arrow" /></Link></div>
                {payments.length ? <div className="activity-list">{payments.slice(0, 5).map((payment) => <div className="activity-row" key={payment.id}><span className="activity-mark"><Icon name="payments" /></span><span className="activity-copy"><strong>{payment.reference}</strong><small>{new Date(payment.date).toLocaleDateString()} · {payment.method.replaceAll("_", " ")}</small></span><span className="activity-amount">KSh {Number(payment.amount).toLocaleString()}</span></div>)}</div> : <div className="empty-state"><strong>No payment records yet</strong>When your tenant profile is linked, your payment history will appear here.</div>}
              </section>
              <section className="panel">
                <div className="panel-heading"><div><h2 className="panel-title">Your maintenance</h2><p className="panel-description">Submit an issue and keep track of your requests.</p></div></div>
                <div className="activity-list">{jobs.slice(0, 4).map((job) => <div className="activity-row" key={job.id}><span className="activity-mark"><Icon name="maintenance" /></span><span className="activity-copy"><strong>{job.issue}</strong><small>{job.job_id} · {new Date(job.date).toLocaleDateString()}</small></span><span className={`status-pill ${statusClass("status", job.status)}`}>{job.status.replaceAll("_", " ")}</span></div>)}</div>
                {!tenantProfile && <div className="hint-card"><strong>Tenant record not linked</strong>Your manager needs to link your account to a tenant and unit record before requests can be associated with your home.</div>}
                <Link className="button button-primary" href="/dashboard/maintenance" style={{ marginTop: 16 }}><Icon name="add" />Open maintenance</Link>
              </section>
            </div>
          </>
        )}
      </section>
    );
  }

  if (role === "maintenance") {
    return (
      <section>
        <PageHeader title={roleTitle} eyebrow="Service work orders" description="Review maintenance records available to your service account." icon="maintenance" />
        {error && <div className="error-state" role="alert"><span>{error}</span><button className="button button-secondary" onClick={() => void load()} type="button">Try again</button></div>}
        {loading ? <div className="loading-state" role="status">Loading work orders...</div> : (
          <>
            <div className="metric-grid">
              <Metric label="Work orders" value={jobs.length} note="Returned by maintenance API" icon="maintenance" />
              <Metric label="Assigned" value={jobs.filter((job) => job.status === "assigned").length} note="Awaiting work" icon="calendar" />
              <Metric label="In progress" value={jobs.filter((job) => job.status === "in_progress").length} note="Active work orders" icon="analytics" />
              <Metric label="Completed" value={jobs.filter((job) => job.status === "completed").length} note="Marked complete" icon="check" />
            </div>
            <section className="panel">
              <div className="panel-heading"><div><h2 className="panel-title">Recent work orders</h2><p className="panel-description">Only work orders assigned to your service account appear here.</p></div><Link className="button button-secondary" href="/dashboard/maintenance">View work orders <Icon name="arrow" /></Link></div>
              {jobs.slice(0, 6).length ? <div className="activity-list">{jobs.slice(0, 6).map((job) => <div className="activity-row" key={job.id}><span className="activity-mark"><Icon name="maintenance" /></span><span className="activity-copy"><strong>{job.issue}</strong><small>{job.job_id} · {job.property_name}{job.unit_number ? ` · ${job.unit_number}` : ""}</small></span><span className={`status-pill ${statusClass("status", job.status)}`}>{job.status.replaceAll("_", " ")}</span></div>)}</div> : <div className="empty-state"><strong>No work orders yet</strong>New service records will appear here.</div>}
            </section>
          </>
        )}
      </section>
    );
  }

  if (role === "admin") {
    const pendingTenantAccess = adminUsers.filter((item) => item.role === "tenant" && !item.portal_access_granted).length;
    return (
      <section>
        <PageHeader title="System administration" eyebrow="Account governance" description="Provision roles, manage active accounts and review system configuration. Property operations and private conversations are not part of this view." icon="settings" actions={<Link className="button button-primary" href="/dashboard/staff"><Icon name="staff" />Manage users</Link>} />
        {error && <div className="error-state" role="alert"><span>{error}</span><button className="button button-secondary" onClick={() => void load()} type="button">Try again</button></div>}
        {loading ? <div className="loading-state" role="status">Loading user registry...</div> : !error && (
          <>
            <div className="metric-grid">
              <Metric label="Registered accounts" value={adminUsers.length} note="Across all provisioned roles" icon="staff" />
              <Metric label="Pending tenant access" value={pendingTenantAccess} note="Managers grant access when linking a tenant record" icon="tenants" />
              <Metric label="Active accounts" value={adminUsers.filter((item) => item.is_active_user).length} note="Enabled in the account registry" icon="check" />
              <Metric label="Direct unit assignments" value={adminUsers.reduce((total, item) => total + item.assigned_units.length, 0)} note="Staff otherwise inherit their manager’s portfolio" icon="properties" />
            </div>
            <div className="dashboard-grid">
              <section className="panel"><div className="panel-heading"><div><h2 className="panel-title">Role provisioning</h2><p className="panel-description">Only administrators can grant manager and staff roles.</p></div></div><Link className="button button-primary" href="/dashboard/staff">Open user access</Link></section>
              <section className="panel"><div className="panel-heading"><div><h2 className="panel-title">System configuration</h2><p className="panel-description">Review the API connection and appearance settings.</p></div></div><Link className="button button-secondary" href="/dashboard/settings">Open settings</Link></section>
            </div>
          </>
        )}
      </section>
    );
  }

  if (role === "staff") {
    return (
      <section>
        <PageHeader title="Agency staff workspace" eyebrow="Shared portfolio operations" description="You can work with the properties and units managed by the manager who onboarded you, plus any units an administrator assigned directly. Financial ledgers stay restricted to managers." icon="dashboard" actions={<Link className="button button-secondary" href="/dashboard/tenancy-events"><Icon name="calendar" />Move workflow</Link>} />
        {error && <div className="error-state" role="alert"><span>{error}</span><button className="button button-secondary" onClick={() => void load()} type="button">Try again</button></div>}
        {loading ? <div className="loading-state" role="status">Loading portfolio operations...</div> : !error && (
          <div className="metric-grid">
            <Metric label="Properties in scope" value={stats?.total_properties ?? 0} note="Contains a unit you can work with" icon="properties" />
            <Metric label="Tenant records" value={stats?.total_tenants ?? 0} note={`${stats?.active_leases ?? 0} active leases`} icon="tenants" />
            <Metric label="Occupied units" value={stats?.occupied_units ?? 0} note="Within your access scope" icon="home" />
            <Metric label="Open work orders" value={jobs.filter((job) => job.status !== "completed").length} note="For properties in your scope" icon="maintenance" />
          </div>
        )}
      </section>
    );
  }

  return (
    <section>
      <PageHeader title={roleTitle} eyebrow="SmartNest · Property operations" description="A clear view of the records and activity currently available from your workspace." icon="dashboard" actions={["admin", "manager", "staff"].includes(role) ? <Link className="button button-secondary" href="/dashboard/properties"><Icon name="properties" />View properties</Link> : undefined} />
      {error && <div className="error-state" role="alert"><span>{error}</span><button className="button button-secondary" onClick={() => void load()} type="button">Try again</button></div>}
      {loading ? <div className="loading-state" role="status">Loading portfolio data...</div> : (
        <>
          <div className="metric-grid">
            <Metric label="Properties" value={metricValue(stats?.total_properties)} note="Across the current portfolio" icon="properties" />
            <Metric label="Tenants" value={metricValue(stats?.total_tenants)} note={`${metricValue(stats?.active_leases)} active leases`} icon="tenants" />
            <Metric label="Recorded rent received" value={stats?.rental_income ?? "—"} note={`${payments.length} payment records returned`} icon="payments" />
            <Metric label="Open work orders" value={jobs.filter((job) => job.status !== "completed").length} note={`${jobs.length} total maintenance records`} icon="maintenance" />
          </div>
          <div className="dashboard-grid">
            <section className="panel">
              <div className="panel-heading"><div><h2 className="panel-title">Recent payments</h2><p className="panel-description">Latest transactions returned by the payment ledger.</p></div><Link className="button button-secondary" href="/dashboard/reconciliation">View ledger <Icon name="arrow" /></Link></div>
              {recentPayments.length ? (
                <div className="activity-list">
                  {recentPayments.map((payment) => (
                    <div className="activity-row" key={payment.id}><span className="activity-mark"><Icon name="payments" /></span><span className="activity-copy"><strong>{payment.tenant_name || payment.reference}</strong><small>{payment.reference} · {payment.date}</small></span><span className="activity-amount">KSh {Number(payment.amount).toLocaleString()}</span></div>
                  ))}
                </div>
              ) : <div className="empty-state"><strong>No payment activity yet</strong>When payments are recorded, the latest entries will show here.</div>}
            </section>
            <section className="panel">
              <div className="panel-heading"><div><h2 className="panel-title">Occupancy</h2><p className="panel-description">Calculated from the unit counts in the dashboard API.</p></div><span className="status-pill green">Live data</span></div>
              <div className="occupancy-row">
                <div className="occupancy-ring" style={{ "--occupancy": `${occupancyRate}%` } as CSSProperties}><div className="occupancy-ring-inner"><strong>{occupancyRate}%</strong><small>occupied</small></div></div>
                <div className="mini-stats">
                  <div className="mini-stat"><span>Occupied units</span><strong>{stats?.occupied_units ?? 0}</strong></div>
                  <div className="mini-stat"><span>Vacant units</span><strong>{stats?.vacant_units ?? 0}</strong></div>
                  <div className="mini-stat"><span>Active work orders</span><strong>{jobs.filter((job) => job.status !== "completed").length}</strong></div>
                </div>
              </div>
            </section>
          </div>
        </>
      )}
    </section>
  );
}

export function AnalyticsPage() {
  const [payments, setPayments] = useState<Payment[]>([]);
  const [properties, setProperties] = useState<Property[]>([]);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([paymentsAPI.list(), propertiesAPI.list(), expensesAPI.list()])
      .then(([paymentsResponse, propertiesResponse, expensesResponse]) => {
        setPayments(paymentsResponse.data);
        setProperties(propertiesResponse.data);
        setExpenses(expensesResponse.data);
      })
      .catch(() => setError("Analytics could not be loaded from the service."))
      .finally(() => setLoading(false));
  }, []);

  const months = useMemo(() => {
    const current = new Date();
    return Array.from({ length: 6 }, (_, index) => {
      const date = new Date(current.getFullYear(), current.getMonth() - (5 - index), 1);
      const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
      const total = payments.filter((payment) => payment.date.startsWith(key)).reduce((sum, payment) => sum + Number(payment.amount), 0);
      return { key, label: date.toLocaleDateString(undefined, { month: "short" }), total };
    });
  }, [payments]);
  const totalPayments = payments.reduce((sum, payment) => sum + Number(payment.amount), 0);
  const totalExpenses = expenses.reduce((sum, expense) => sum + Number(expense.amount), 0);
  const maxMonth = Math.max(...months.map((month) => month.total), 1);

  return (
    <section>
      <PageHeader title="Analytics" eyebrow="Portfolio performance" description="Explore payments, expenses and occupancy using live records from the SmartNest API." icon="analytics" />
      {error && <div className="error-state" role="alert">{error}</div>}
      {loading ? <div className="loading-state" role="status">Loading analytics...</div> : (
        <>
          <div className="metric-grid">
            <Metric label="Payments recorded" value={payments.length} note={`KSh ${totalPayments.toLocaleString()} total`} icon="payments" />
            <Metric label="Expense records" value={expenses.length} note={`KSh ${totalExpenses.toLocaleString()} total`} icon="expenses" />
            <Metric label="Properties" value={properties.length} note="Returned by the property service" icon="properties" />
            <Metric label="Occupied units" value={properties.reduce((sum, item) => sum + item.occupied_units, 0)} note={`Of ${properties.reduce((sum, item) => sum + item.total_units, 0)} listed units`} icon="home" />
          </div>
          <div className="dashboard-grid">
            <section className="panel">
              <div className="panel-heading"><div><h2 className="panel-title">Monthly payments</h2><p className="panel-description">Recorded payment totals for the last six calendar months.</p></div></div>
              <div className="chart" role="img" aria-label="Payment totals by month">
                {months.map((month) => <div className="chart-column" key={month.key}><div className="chart-bar" style={{ height: `${(month.total / maxMonth) * 100}%` }} title={`KSh ${month.total.toLocaleString()}`} /><span>{month.label}</span></div>)}
              </div>
            </section>
            <section className="panel">
              <div className="panel-heading"><div><h2 className="panel-title">Portfolio snapshot</h2><p className="panel-description">Occupancy calculated from actual property records.</p></div></div>
              <div className="activity-list">
                {properties.length ? properties.slice(0, 5).map((property) => (
                  <div className="activity-row" key={property.id}><span className="activity-mark"><Icon name="properties" /></span><span className="activity-copy"><strong>{property.name}</strong><small>{property.location}</small></span><span className="activity-amount">{property.total_units ? Math.round(property.occupied_units / property.total_units * 100) : 0}%</span></div>
                )) : <div className="empty-state"><strong>No properties available</strong>Add property records to see portfolio details.</div>}
              </div>
            </section>
          </div>
          <p className="panel-description" style={{ marginTop: 16 }}>This view summarizes saved records; the API does not currently return historical comparisons or rent forecasts.</p>
        </>
      )}
    </section>
  );
}

export function ProfilePage() {
  const { user, refreshProfile } = useAuth();
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [avatarError, setAvatarError] = useState("");
  const [photoSaving, setPhotoSaving] = useState(false);
  const [photoMenuOpen, setPhotoMenuOpen] = useState(false);
  const photoInput = useRef<HTMLInputElement>(null);
  const [cropFile, setCropFile] = useState<File | null>(null);

  const choosePhoto = (file: File) => {
    setPhotoMenuOpen(false);
    setAvatarError("");
    if (file.size > 5 * 1024 * 1024) {
      setAvatarError("Profile photos must be 5 MB or smaller.");
      return;
    }
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      setAvatarError("Choose a JPEG, PNG, or WebP profile photo.");
      return;
    }
    setCropFile(file);
  };

  const updatePhoto = async (file?: File) => {
    setPhotoMenuOpen(false);
    setAvatarError("");
    setMessage("");
    if (file && file.size > 5 * 1024 * 1024) {
      setAvatarError("Profile photos must be 5 MB or smaller.");
      return false;
    }
    if (file && !["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      setAvatarError("Choose a JPEG, PNG, or WebP profile photo.");
      return false;
    }
    setPhotoSaving(true);
    try {
      await authAPI.updateProfile(file ? { avatar_image: file } : { remove_avatar: true });
      await refreshProfile();
      window.dispatchEvent(new Event("smartnest:avatar-updated"));
      setMessage(file ? "Your profile photo has been updated." : "Your profile photo has been removed.");
      return true;
    } catch {
      setAvatarError("We couldn’t update your profile photo. Please try again.");
      return false;
    } finally {
      setPhotoSaving(false);
    }
  };
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [passwordError, setPasswordError] = useState("");
  const [passwordMessage, setPasswordMessage] = useState("");
  const name = user?.username || user?.email || "SmartNest user";

  const saveProfile = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    const form = new FormData(event.currentTarget);
    try {
      await authAPI.updateProfile({
        username: String(form.get("username") ?? ""),
        phone: String(form.get("phone") ?? ""),
      });
      await refreshProfile();
      window.dispatchEvent(new Event("smartnest:avatar-updated"));
      setMessage("Your profile has been updated.");
    } catch {
      setMessage("We couldn’t update your profile. Check the details and try again.");
    } finally {
      setSaving(false);
    }
  };

  const changePassword = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPasswordSaving(true);
    setPasswordError("");
    setPasswordMessage("");
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const newPassword = String(form.get("new_password1") ?? "");
    const confirmPassword = String(form.get("new_password2") ?? "");
    if (newPassword !== confirmPassword) {
      setPasswordError("The new passwords don’t match.");
      setPasswordSaving(false);
      return;
    }
    try {
      await authAPI.changePassword({
        current_password: String(form.get("current_password") ?? ""),
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
      setPasswordMessage("Your password has been updated. Sign in again with your new password.");
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      localStorage.removeItem("user");
      formElement.reset();
      window.setTimeout(() => router.replace("/login?password_changed=1"), 900);
    } catch (requestError) {
      const response = typeof requestError === "object" && requestError !== null && "response" in requestError
        ? (requestError as { response?: { data?: Record<string, unknown> } }).response
        : undefined;
      const errors = response?.data;
      const firstError = errors ? Object.values(errors).flatMap((value) => Array.isArray(value) ? value : [value]).find((value) => typeof value === "string") : undefined;
      setPasswordError(typeof firstError === "string" ? firstError : "We couldn’t update your password. Check the current password and try again.");
    } finally {
      setPasswordSaving(false);
    }
  };

  return (
    <section>
      {cropFile && <ProfilePhotoCropper file={cropFile} onCancel={() => setCropFile(null)} onSave={async (file) => {
        const saved = await updatePhoto(file);
        if (saved) setCropFile(null);
        return saved;
      }} />}
      <PageHeader title="My profile" eyebrow="Account" description="Account details are read from your authenticated SmartNest profile." icon="profile" />
      <div className="panel profile-card">
        <div className="profile-photo-control">
          <UserAvatar userId={user?.id} hasAvatar={user?.has_avatar} name={name} className="profile-avatar" />
          <button className="profile-camera" type="button" aria-label="Edit profile photo" aria-expanded={photoMenuOpen} aria-controls="profile-photo-options" disabled={photoSaving || saving}
            onClick={() => setPhotoMenuOpen((open) => !open)}><Icon name="camera" /></button>
          <input ref={photoInput} type="file" hidden accept="image/jpeg,image/png,image/webp" aria-label="Choose profile photo"
            onChange={(event) => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ""; if (file) choosePhoto(file); }} />
          {photoMenuOpen && <div className="profile-photo-options" id="profile-photo-options" onKeyDown={(event) => { if (event.key === "Escape") { setPhotoMenuOpen(false); event.currentTarget.parentElement?.querySelector<HTMLButtonElement>(".profile-camera")?.focus(); } }}>
            <button type="button" onClick={() => photoInput.current?.click()}>{user?.has_avatar ? "Change photo" : "Add photo"}</button>
            {user?.has_avatar && <button type="button" onClick={() => void updatePhoto()}>Remove photo</button>}
            <button type="button" onClick={() => setPhotoMenuOpen(false)}>Cancel</button>
          </div>}
        </div>
        <div><h2>{name}</h2><p>{user?.email}</p></div>
      </div>
      <section className="panel form-panel">
        <div className="panel-heading"><div><h2 className="panel-title">Account information</h2><p className="panel-description">Update your name, contact phone, and profile photo. Photos are only visible to your account and people connected to your property or work assignments.</p></div></div>
        <form onSubmit={saveProfile}>
          <div className="form-grid">
            <div className="field"><label htmlFor="profile-name">Full name</label><input id="profile-name" name="username" required maxLength={150} defaultValue={user?.username ?? ""} /></div>
            <div className="field"><label htmlFor="profile-phone">Phone number</label><input id="profile-phone" name="phone" type="tel" maxLength={20} defaultValue={user?.phone ?? ""} /></div>
            <div className="field"><label htmlFor="profile-email">Email address</label><input id="profile-email" value={user?.email ?? ""} readOnly /></div>
            <div className="field"><label htmlFor="profile-role">Role</label><input id="profile-role" value={user?.role ?? ""} readOnly /></div>
          </div>
          {avatarError && <div className="form-error" role="alert">{avatarError}</div>}
          {message && <div className="form-message" role="status">{message}</div>}
          <div className="form-actions"><button className="button button-primary" type="submit" disabled={saving || photoSaving}>{saving ? "Saving..." : "Save profile"}</button></div>
        </form>
      </section>
      <section className="panel form-panel" id="password">
        <div className="panel-heading"><div><h2 className="panel-title">Change your password</h2><p className="panel-description">Use a unique password. You’ll be asked to sign in again after changing it.</p></div></div>
        {passwordError && <div className="auth-message" role="alert">{passwordError}</div>}
        {passwordMessage && <div className="auth-message success" role="status">{passwordMessage}</div>}
        <form className="auth-form password-change-form" onSubmit={changePassword}>
          <div className="field"><label htmlFor="current-password">Current password</label><PasswordInput className="auth-input" id="current-password" name="current_password" autoComplete="current-password" required /></div>
          <div className="field"><label htmlFor="new-password">New password</label><PasswordInput className="auth-input" id="new-password" name="new_password1" autoComplete="new-password" minLength={8} required /></div>
          <div className="field"><label htmlFor="repeat-new-password">Repeat new password</label><PasswordInput className="auth-input" id="repeat-new-password" name="new_password2" autoComplete="new-password" minLength={8} required /></div>
          <div className="form-actions"><button className="button button-primary" type="submit" disabled={passwordSaving}>{passwordSaving ? "Updating..." : "Change password"}</button></div>
        </form>
      </section>
    </section>
  );
}

export function HelpPage() {
  const {user}=useAuth();
  const role=user?.role||"";
  const showAccessGuide=role==="admin"||role==="manager";
  const links = [
    { icon: "properties", title: "Manage properties", description: "Add a property, then register its units.", href: "/dashboard/properties" },
    { icon: "tenants", title: "Maintain lease records", description: "Keep tenant contact and lease end dates current.", href: "/dashboard/tenants" },
    { icon: "payments", title: "Review payments", description: "Check payment references and match statuses.", href: "/dashboard/reconciliation" },
    { icon: "maintenance", title: "Coordinate repairs", description: "Track maintenance work orders and assignments.", href: "/dashboard/maintenance" },
    { icon: "notices", title: "Read notices", description: "View communication records stored in the workspace.", href: "/dashboard/notices" },
    { icon: "profile", title: "Account details", description: "Check the profile fields associated with your login.", href: "/dashboard/profile" },
  ];
  return (
    <section>
      <PageHeader title="Help & support" eyebrow="Account" description="Quick routes to common property operations." icon="help" /><section className="panel flow-card"><h2>Contact SmartNest</h2><p>Operated by {operator.name}. Support hours: {operator.supportHours}.</p><p><a href={`mailto:${operator.supportEmail}`}>{operator.supportEmail}</a></p><p>{operator.tenancyRetention}</p></section>
      <div className="support-grid">{links.map((link) => <article className="panel support-card" key={link.href}><span className="metric-icon"><Icon name={link.icon} /></span><h3>{link.title}</h3><p>{link.description}</p><Link className="button button-secondary" href={link.href}>Open <Icon name="arrow" /></Link></article>)}</div>
      <AdministratorSupport role={role}/>
      {showAccessGuide && <section className="panel role-workflow-panel">
        <div className="panel-heading"><div><h2 className="panel-title">Who can see and manage what?</h2><p className="panel-description">Access follows the work each person needs to do.</p></div></div>
        <div className="role-workflow-list">
          <p><strong>System administrator</strong><span>Manages accounts, roles, and which properties belong to each manager. Admin access to conversations and tenant records is limited unless needed for administration.</span></p>
          <p><strong>Property manager</strong><span>Manages only assigned properties and their units, tenants, payments, expenses, maintenance, and handovers. Creates staff and maintenance accounts and invites tenants.</span></p>
          <p><strong>Staff</strong><span>Works with the portfolio of the manager who onboarded them, plus any units an administrator assigns directly. Sees tenant and lease records for that scope, can record inspections, check-ins, check-outs, and work orders, and can create tenant invitation links. Payments and expenses remain manager-only.</span></p>
          <p><strong>Maintenance</strong><span>Sees only work orders assigned to their account, along with the tenant and property contact details needed to complete each job. Cannot browse the wider tenant or property directory.</span></p>
          <p><strong>Tenant</strong><span>Sees their linked tenancy, payments, and maintenance requests. Can raise repair requests and contact permitted property contacts.</span></p>
        </div>
        <p className="panel-description role-workflow-note">This is a product access summary, not legal advice. In Kenya, the Data Protection Act 2019 requires personal data to be handled lawfully, fairly, transparently, for a specific purpose, and with appropriate safeguards. SmartNest&apos;s owner remains responsible for confirming the lawful basis, notices, retention period, and access/rectification process for their use.</p>
        <a className="button button-secondary" href="https://www.odpc.go.ke/data-protection-laws-kenya/" target="_blank" rel="noreferrer">Read Kenya ODPC guidance</a>
      </section>}
    </section>
  );
}

export function SettingsPage() {
  const [status, setStatus] = useState("Not checked");
  const [detail, setDetail] = useState("Check the configured API health endpoint.");
  const [checking, setChecking] = useState(false);

  const checkService = async () => {
    setChecking(true);
    try {
      const response = await healthAPI.check();
      setStatus("Connected");
      setDetail(`${response.data.service} · ${response.data.status}`);
    } catch (error) {
      setStatus("Unavailable");
      setDetail(error instanceof Error ? error.message : "The API health check failed.");
    } finally {
      setChecking(false);
    }
  };

  return (
    <section>
      <PageHeader title="Settings" eyebrow="Administration" description="Review the API connection and your locally saved appearance preference." icon="settings" />
      <div className="dashboard-grid">
        <section className="panel">
          <div className="panel-heading"><div><h2 className="panel-title">Backend connection</h2><p className="panel-description">The API endpoint is configured by the frontend deployment environment.</p></div><span className={`status-pill ${status === "Connected" ? "green" : status === "Unavailable" ? "danger" : ""}`}>{status}</span></div>
          <p className="panel-description">{detail}</p>
          <button className="button button-primary" style={{ marginTop: 16 }} type="button" disabled={checking} onClick={() => void checkService()}>{checking ? "Checking..." : "Test API connection"}</button>
        </section>
        <section className="panel">
          <div className="panel-heading"><div><h2 className="panel-title">Appearance</h2><p className="panel-description">Use the theme toggle in the header to change your workspace.</p></div></div>
          <div className="theme-preview"><span className="theme-swatch" /><span><strong>SmartNest green</strong><span className="panel-description" style={{ display: "block" }}>#2E6F40 · Your selection is saved in this browser.</span></span></div>
        </section>
      </div>
    </section>
  );
}

export function NoticesSummary({ notices }: { notices: Notice[] }) {
  return <div>{notices.map((notice) => <div className="notice-card" key={notice.id}><span className="activity-mark"><Icon name="notices" /></span><div className="notice-copy"><strong>{notice.title}</strong><p>{notice.text}</p></div><span className="status-pill">{notice.state}</span></div>)}</div>;
}
