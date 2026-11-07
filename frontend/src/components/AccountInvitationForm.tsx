"use client";

import { useState, type FormEvent } from "react";
import { accountInvitationsAPI } from "@/lib/api";
import {useRecords} from "@/lib/workflows";
import InvitationComposer from "@/components/InvitationComposer";

export default function AccountInvitationForm({ manager = false }: { manager?: boolean }) {
  const properties=useRecords<{id:number;name:string;owner_id:number|null}>(manager?'/invitation-property-options/':'/properties/');
  const units=useRecords<{id:number;property:number;unit_number:string}>(manager?'/invitation-property-options/':'/units/');
  const [property,setProperty]=useState('');
  const [recipient, setRecipient] = useState<{ name: string; email: string; phone: string; role: "manager" | "staff" | "maintenance"; property?:number;unit?:number } | null>(null);
  const [created, setCreated] = useState(false);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setRecipient({ name: String(data.get("name")), email: String(data.get("email")), phone: String(data.get("phone") ?? ""), role: manager ? "manager" : data.get("role") as "staff" | "maintenance",...(property?{property:Number(property)}:{}),...(data.get("unit")?{unit:Number(data.get("unit"))}:{}) });
  };
  return (
    <section className="panel form-panel">
      <div className="panel-heading"><div><h2 className="panel-title">{manager ? "Invite a manager" : "Invite a team member"}</h2><p className="panel-description">{manager ? "The recipient registers directly as a manager." : "The recipient registers with the selected staff or maintenance role and chooses their own password."}</p></div></div>
      {!recipient ? <form onSubmit={submit}>
        <div className="form-grid">
          {!manager && <label className="field"><span>Role</span><select name="role"><option value="staff">Staff</option><option value="maintenance">Maintenance</option></select></label>}
          <label className="field"><span>Relevant property (optional)</span><select value={property} onChange={e=>setProperty(e.target.value)}><option value="">{manager?'Assign property later':'My portfolio'}</option>{properties.items.map(x=><option value={x.id} key={x.id}>{x.name}</option>)}</select></label>
          {!manager&&property&&<label className="field"><span>Relevant unit (optional)</span><select name="unit" key={property}><option value="">All current units in this property</option>{units.items.filter(u=>String(u.property)===property).map(u=><option key={u.id} value={u.id}>{u.unit_number}</option>)}</select></label>}
          <label className="field"><span>Full name</span><input name="name" required maxLength={150} autoComplete="name" /></label>
          <label className="field"><span>Email address</span><input name="email" type="email" required maxLength={254} autoComplete="email" /></label>
          <label className="field"><span>Phone number</span><input name="phone" type="tel" maxLength={20} autoComplete="tel" /></label>
        </div>
        <div className="form-actions"><button className="button button-primary" type="submit">Continue to invitation</button></div>
      </form> : <>
        <p><strong>{recipient.name}</strong> · {recipient.role}</p>
        <InvitationComposer key={`${recipient.email}:${recipient.role}`} name={recipient.name} defaultEmail={recipient.email} prepare={async (email) => {
          const { data } = await accountInvitationsAPI.create({ ...recipient, email });
          setCreated(true);
          const url = new URL("/join-account", window.location.origin);
          url.searchParams.set("token", data.token);
          return url.toString();
        }} />
        <div className="form-actions">
          {!created && <button className="button button-secondary" type="button" onClick={() => setRecipient(null)}>Edit details</button>}
          <button className="button button-secondary" type="button" onClick={() => { setRecipient(null); setCreated(false); }}>Invite another person</button>
        </div>
      </>}
    </section>
  );
}
