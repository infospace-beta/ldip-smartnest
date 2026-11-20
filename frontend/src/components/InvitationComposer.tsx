"use client";
import {useRef,useState,type FormEvent} from 'react';
import {getApiErrorMessage} from '@/lib/api';
import InvitationShare from '@/components/InvitationShare';

export default function InvitationComposer({name,defaultEmail='',prepare}:{name:string;defaultEmail?:string;prepare:(email:string)=>Promise<string>}) {
  const [email,setEmail]=useState(defaultEmail),[busy,setBusy]=useState(false),[error,setError]=useState(''),[link,setLink]=useState('');
  const inFlight=useRef(false);
  const prepareLink=async(event:FormEvent<HTMLFormElement>)=>{
    event.preventDefault();if(inFlight.current||link)return;inFlight.current=true;setBusy(true);setError('');
    try{setLink(await prepare(email.trim().toLowerCase()));}
    catch(e){setError(getApiErrorMessage(e,'Could not prepare the invitation. Please try again.'));}
    finally{inFlight.current=false;setBusy(false);}
  };
  return <form className="invitation-composer" onSubmit={prepareLink}>
    <label className="field"><span>Recipient email</span><input type="email" required maxLength={254} autoComplete="email" value={email} disabled={busy||Boolean(link)} onChange={e=>setEmail(e.target.value)}/></label>
    <p className="panel-description">Create the registration link for {name}, then share it by email, WhatsApp or SMS.</p>
    {!link&&<div><button className="button button-primary" type="submit" disabled={busy}>{busy?'Preparing...':'Create invitation link'}</button></div>}
    {link&&<div className="hint-card invite-link-card"><strong>Invitation link ready</strong><InvitationShare link={link} email={email} name={name}/><small>This one-time invitation is valid for seven days from creation.</small></div>}
    {error&&<p role="alert" className="form-error">{error}</p>}
  </form>;
}
