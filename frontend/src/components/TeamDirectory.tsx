"use client";
import {useState} from 'react';
import api,{getApiErrorMessage} from '@/lib/api';
import {useRecords} from '@/lib/workflows';
import AccountInvitationForm from '@/components/AccountInvitationForm';
import InvitationShare from '@/components/InvitationShare';

interface TeamRecord {
  id:string;name:string;email:string;phone:string;role:'staff'|'maintenance';
  status:'active'|'inactive'|'pending'|'expired'|'unavailable';
  invitation_id:string|null;expires_at:string|null;can_invite:boolean;
}
const statuses={active:'Account active',inactive:'Account inactive',pending:'Invitation pending',expired:'Invitation expired',unavailable:'Invitation unavailable'};

export default function TeamDirectory(){
  const team=useRecords<TeamRecord>('/team/');
  const [search,setSearch]=useState(''),[role,setRole]=useState('');
  const [selected,setSelected]=useState<TeamRecord|null>(null),[link,setLink]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const rows=team.items.filter(person=>(!role||person.role===role)&&[person.name,person.email,person.phone].some(value=>value.toLowerCase().includes(search.toLowerCase())));
  const share=async(person:TeamRecord)=>{
    if(busy)return;
    setSelected(person);setLink('');setError('');setBusy(true);
    try{
      const {data}=await api.post<{token:string}>(`/team/invitations/${person.invitation_id}/link/`);
      const target=new URL('/join-account',window.location.origin);target.searchParams.set('token',data.token);setLink(target.href);
      await team.load();
    }catch(e){setError(getApiErrorMessage(e,'Could not prepare this invitation.'));}
    finally{setBusy(false);}
  };
  return <section>
    <header className="flow-heading"><div><div className="page-eyebrow">Manager workspace</div><h1>My team</h1><p>Your staff, maintenance team and outstanding invitations.</p></div><a className="button button-primary" href="#invite-team">Invite a team member</a></header>
    <section className="panel flow-card" aria-labelledby="team-list-heading">
      <div className="panel-heading"><div><h2 className="panel-title" id="team-list-heading">Staff &amp; maintenance</h2><p className="panel-description">{team.items.length} team records. Accepted accounts and pending invitations stay visible here.</p></div><button type="button" className="button button-secondary" disabled={team.loading} onClick={()=>void team.load()}>Refresh</button></div>
      <div className="form-grid"><label className="field"><span>Search team</span><input type="search" value={search} onChange={event=>setSearch(event.target.value)} placeholder="Name, email or phone"/></label><label className="field"><span>Role</span><select value={role} onChange={event=>setRole(event.target.value)}><option value="">All team members</option><option value="staff">Staff</option><option value="maintenance">Maintenance</option></select></label></div>
      {team.error&&<p className="form-error" role="alert">{team.error}</p>}
      {team.loading?<p role="status">Loading your team...</p>:<div className="table-wrap"><table className="data-table"><thead><tr><th>Name</th><th>Role</th><th>Email</th><th>Phone</th><th>Account status</th><th>Invitation</th></tr></thead><tbody>
        {rows.map(person=><tr key={person.id}><td><strong>{person.name}</strong></td><td>{person.role==='staff'?'Staff':'Maintenance'}</td><td>{person.email}</td><td>{person.phone||'Not provided'}</td><td>{statuses[person.status]}</td><td>{person.can_invite?<button type="button" className="button button-secondary button-compact" disabled={busy} onClick={()=>void share(person)}>{person.status==='expired'?'Renew invitation link':'Share invitation link'}</button>:person.status==='active'?'Already joined':person.status==='inactive'?'Contact your administrator':'Update the invitation property'}</td></tr>)}
        {!rows.length&&<tr><td colSpan={6}>{team.items.length?'No team members match your search.':'No team members yet. Create an invitation below to add staff or maintenance.'}</td></tr>}
      </tbody></table></div>}
    </section>
    {selected&&<section className="panel flow-card" aria-labelledby="team-invitation-heading"><div className="panel-heading"><div><h2 id="team-invitation-heading" className="panel-title">Invitation for {selected.name}</h2><p>{selected.email}</p></div><button type="button" className="button button-secondary" disabled={busy} onClick={()=>{setSelected(null);setLink('');}}>Close</button></div>{busy&&<p role="status">Preparing invitation...</p>}{error&&<p role="alert" className="form-error">{error}</p>}{link&&<InvitationShare link={link} email={selected.email} name={selected.name}/>}</section>}
    <div id="invite-team" style={{marginTop:24}}><AccountInvitationForm onCreated={team.load}/></div>
  </section>;
}
