"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { propertiesAPI, unitsAPI, tenantsAPI, getApiErrorMessage, type Property, type Unit, type Tenant } from "@/lib/api";
import InvitationComposer from "@/components/InvitationComposer";
import Icon from "@/components/Icon";

function TenantCheckIn({ unit, onSaved, onBack }: { unit: Unit; onSaved: () => Promise<void>; onBack: () => void }) {
  const [step, setStep] = useState(1);
  const [returning, setReturning] = useState(false);
  const [details, setDetails] = useState({ name: "", phone: "", email: "", lease_end: "", rent: unit.rent });
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const lock = useRef(false);
  const checkIn = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (lock.current) return;
    lock.current = true;
    setSaving(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const file = form.get("evidence_upload");
      const { data } = await unitsAPI.checkIn(unit.property, unit.id, {
        ...details, notes: String(form.get("notes") ?? ""),
        account_email: returning ? details.email : undefined,
        evidence_upload: file instanceof File && file.size ? file : undefined,
      });
      setTenant(data);
      setStep(3);
      // A directory refresh failure must never turn a saved check-in into a retry.
      void onSaved();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Check-in could not be completed. Please try again."));
    } finally {
      lock.current = false;
      setSaving(false);
    }
  };
  return <section className="panel form-panel">
    <div className="panel-heading"><div><h2 className="panel-title">{unit.property_name} · House {unit.unit_number}</h2><p className="panel-description">Tenant details → Check-in → Invitation</p></div><button type="button" className="button button-secondary" disabled={saving} onClick={onBack}>Back to houses</button></div>
    <ol className="onboarding-steps" aria-label="Tenant onboarding progress">{["Tenant details", "Check-in", "Invitation"].map((title, index) => <li key={title} aria-current={step === index + 1 ? "step" : undefined}>{index + 1}. {title}</li>)}</ol>
    {error && <p className="form-error" role="alert">{error}</p>}
    {step === 1 && <form onSubmit={(event) => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      setDetails({ name: String(form.get("name")), phone: String(form.get("phone")), email: String(form.get("email")), lease_end: String(form.get("lease_end")), rent: String(form.get("rent")) });
      setStep(2);
    }}>
      <div className="form-grid">
        <label className="field"><span>Tenant full name</span><input required maxLength={200} name="name" value={details.name} onChange={(event) => setDetails({ ...details, name: event.target.value })} /></label>
        <label className="field"><span>Phone number</span><input type="tel" required maxLength={20} name="phone" value={details.phone} onChange={(event) => setDetails({ ...details, phone: event.target.value })} /></label>
        <label className="field"><span>Tenant email</span><input type="email" required maxLength={254} name="email" value={details.email} onChange={(event) => setDetails({ ...details, email: event.target.value })} /></label>
        <label className="consent-row field-full"><input type="checkbox" checked={returning} onChange={(event) => setReturning(event.target.checked)} /><span>Returning tenant with an existing verified SmartNest account. Link this email after check-in and preserve previous tenancy records.</span></label>
        <label className="field"><span>Lease end date</span><input type="date" required name="lease_end" value={details.lease_end} onChange={(event) => setDetails({ ...details, lease_end: event.target.value })} /></label>
        <label className="field"><span>Monthly rent</span><input required maxLength={50} name="rent" value={details.rent} onChange={(event) => setDetails({ ...details, rent: event.target.value })} /></label>
      </div>
      <div className="form-actions"><button className="button button-primary" type="submit">Continue to check-in</button></div>
    </form>}
    {step === 2 && <form onSubmit={checkIn}>
      <div className="hint-card"><strong>{details.name}</strong>{unit.property_name} · House {unit.unit_number}<br />{details.phone} · {details.email}<br />Rent: {details.rent} · Lease ends: {details.lease_end}</div>
      <div className="form-grid">
        <label className="field field-full"><span>Handover notes</span><textarea name="notes" rows={3} /></label>
        <label className="field field-full"><span>Handover photo (optional)</span><input name="evidence_upload" type="file" accept="image/jpeg,image/png,image/webp" /><small className="field-hint">JPEG, PNG or WebP. Maximum 5 MB.</small></label>
        <label className="consent-row field-full"><input type="checkbox" required /><span>I confirm the handover and tenant check-in are complete.</span></label>
      </div>
      <div className="form-actions"><button type="button" className="button button-secondary" disabled={saving} onClick={() => setStep(1)}>Edit tenant details</button><button type="submit" className="button button-primary" disabled={saving}>{saving ? "Checking in…" : "Complete check-in"}</button></div>
    </form>}
    {step === 3 && tenant && <>
      <div className="auth-message success" role="status">{tenant.name} is checked in. House {unit.unit_number} is now occupied.</div>
      {tenant.account_linked ? <p>The existing account is linked. The tenant can sign in with their usual credentials; no new password or registration is needed.</p> : <><h3>Send the registration invitation</h3>
      <InvitationComposer name={tenant.name} defaultEmail={details.email} defaultPhone={details.phone} prepare={async (email) => {
        const { data } = await tenantsAPI.invite(tenant.id, email);
        const url = new URL("/join", window.location.origin);
        url.searchParams.set("token", data.token);
        return url.toString();
      }} /></>}
    </>}
  </section>;
}

export default function PropertiesWorkflow() {
  const { user } = useAuth();
  const [properties, setProperties] = useState<Property[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [selectedUnit, setSelectedUnit] = useState<Unit | null>(null);
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const canCheckIn = user?.role === "manager" || user?.role === "staff";
  const load = useCallback(async () => {
    try {
      const [props, houses] = await Promise.all([propertiesAPI.list(), unitsAPI.list()]);
      setProperties(props.data);
      setUnits(houses.data);
      setError("");
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Could not load properties. Please try again."));
    } finally { setLoading(false); }
  }, []);
  useEffect(() => {
    let cancelled = false;

    Promise.all([propertiesAPI.list(), unitsAPI.list()])
      .then(([props, houses]) => {
        if (cancelled) return;
        setProperties(props.data);
        setUnits(houses.data);
        setError("");
      })
      .catch((requestError: unknown) => {
        if (cancelled) return;
        setError(getApiErrorMessage(requestError, "Could not load properties. Please try again."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);
  const create = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setError("");
    const form = new FormData(event.currentTarget);
    const values = Object.fromEntries([...form.entries()].map(([key,value]) => [key,String(value)]));
    try {
      const { data } = await propertiesAPI.create({ ...values, total_units: Number(values.total_units) });
      setSelected(data.id);
      setSelectedUnit(null);
      setCreating(false);
      await load();
    } catch (requestError) { setError(getApiErrorMessage(requestError, "Could not create the property.")); }
    finally { setSaving(false); }
  };
  const property = properties.find((item) => item.id === selected);
  const houses = units.filter((item) => item.property === selected).sort((a, b) => a.unit_number.localeCompare(b.unit_number, undefined, { numeric: true }));
  return <section>
    <div className="page-heading"><div><div className="page-eyebrow">Portfolio</div><h1 className="page-title">Properties &amp; units</h1><p className="page-description">Choose a property, select a vacant house, and complete tenant check-in before sending an invitation.</p></div>{user?.role === "manager" && <button type="button" className="button button-primary" onClick={() => { setCreating(!creating); setSelectedUnit(null); }}><Icon name="add" />{creating ? "Close" : "Add a property"}</button>}</div>
    {error && <div className="error-state" role="alert">{error}<button type="button" className="button button-secondary" onClick={() => void load()}>Refresh</button></div>}
    {creating && <section className="panel form-panel"><h2 className="panel-title">Add a property</h2><p className="panel-description">Houses are created automatically and start vacant.</p><form onSubmit={create}><div className="form-grid">
      <label className="field"><span>Property name</span><input name="name" required maxLength={200} /></label>
      <label className="field"><span>Location</span><input name="location" required maxLength={200} /></label>
      <label className="field"><span>Portfolio / cluster</span><input name="cluster" maxLength={100} defaultValue="Nairobi Cluster" /></label>
      <label className="field"><span>Number of houses</span><input name="total_units" type="number" required min={1} max={1000} step={1} /></label>
      <label className="field"><span>Typical monthly rent</span><input name="monthly_rent" maxLength={50} /></label>
      <label className="field"><span>Property type</span><input name="tag" maxLength={50} placeholder="Residential" /></label>
      <label className="field field-full"><span>Photo URL</span><input name="photo_url" type="url" /></label>
    </div><div className="form-actions"><button type="submit" className="button button-primary" disabled={saving}>{saving ? "Saving…" : "Save property and view houses"}</button></div></form></section>}
    {loading ? <div className="loading-state" role="status">Loading properties…</div> : <>
      {!selectedUnit && <div className="property-flow-grid">{properties.map((item) => <button type="button" className={`panel property-flow-card ${selected === item.id ? "selected" : ""}`} key={item.id} onClick={() => { setSelected(item.id); setCreating(false); }} aria-pressed={selected === item.id}><Icon name="properties" /><strong>{item.name}</strong><span>{item.location}</span><small>{item.total_units} houses · {item.occupied_units} occupied</small></button>)}</div>}
      {!properties.length && !error && <div className="empty-state"><strong>No properties yet</strong>Add a property to create its vacant houses.</div>}
      {property && !selectedUnit && <section className="panel form-panel"><div className="panel-heading"><div><h2 className="panel-title">{property.name} · Houses</h2><p className="panel-description">{canCheckIn ? "Select a vacant house to add a tenant and complete check-in." : "House availability for this property."}</p></div></div><div className="property-flow-grid">{houses.map((unit) => <button type="button" className={`unit-flow-card ${unit.status}`} key={unit.id} disabled={unit.status !== "vacant" || !canCheckIn} onClick={() => setSelectedUnit(unit)}><strong>House {unit.unit_number}</strong><span className={`status-pill ${unit.status === "vacant" ? "green" : ""}`}>{unit.status}</span><span>{unit.unit_type} · {unit.rent}</span>{unit.status === "occupied" && unit.tenant && <small>{unit.tenant}</small>}</button>)}</div>{!houses.length && <p>No houses are available in your assigned scope.</p>}</section>}
      {selectedUnit && <TenantCheckIn key={selectedUnit.id} unit={selectedUnit} onSaved={load} onBack={() => setSelectedUnit(null)} />}
    </>}
  </section>;
}
