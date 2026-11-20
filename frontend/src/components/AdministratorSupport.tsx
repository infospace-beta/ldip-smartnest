"use client";
import Link from 'next/link';
import {useEffect,useRef,useState,type FormEvent} from 'react';
import {communicationAPI,getApiErrorMessage,type CommunicationContact} from '@/lib/api';

export default function AdministratorSupport({role}:{role:string}) {
  const [admins,setAdmins]=useState<CommunicationContact[]>([]),[loading,setLoading]=useState(true);
  const [error,setError]=useState(''),[sent,setSent]=useState(false),[busy,setBusy]=useState(false);
  const submitting=useRef(false);
  const supportEmail=process.env.NEXT_PUBLIC_SUPPORT_EMAIL||'ogonyogad@gmail.com';
  const emailLink=`mailto:${encodeURIComponent(supportEmail)}?subject=SmartNest%20support%20request`;
  const eligible=['manager','tenant','staff','maintenance'].includes(role);
  useEffect(()=>{
    if(!eligible)return;
    let active=true;
    void communicationAPI.contacts().then(({data})=>{if(active)setAdmins(data.filter(contact=>contact.role==='admin'));})
      .catch(()=>{if(active)setError('Administrator contacts could not be loaded. You can use email below, or reload this page to retry.');})
      .finally(()=>{if(active)setLoading(false);});
    return()=>{active=false;};
  },[eligible]);
  if(role==='admin')return <section className="panel support-card" style={{marginTop:20}}><h2 className="panel-title">Administrator support inbox</h2><p>Managers, tenants, staff and maintenance users can message you directly about account or system problems.</p><Link className="button button-primary" href="/dashboard/messages">Open support conversations</Link></section>;
  if(!eligible)return null;
  const submit=async(event:FormEvent<HTMLFormElement>)=>{
    event.preventDefault();if(submitting.current)return;
    const form=event.currentTarget,values=new FormData(form);
    const recipient=Number(values.get('administrator'));
    if(!admins.some(admin=>admin.id===recipient)){setError('Choose an available administrator.');return;}
    submitting.current=true;setBusy(true);setError('');setSent(false);
    try{
      await communicationAPI.startConversation({recipient,subject:`[Support] ${String(values.get('subject')||'').trim()}`,body:String(values.get('body')||'').trim()});
      setSent(true);form.reset();
    }catch(e){setError(getApiErrorMessage(e,'Your support message could not be sent. Try again or use email below.'));}
    finally{submitting.current=false;setBusy(false);}
  };
  return <section className="panel support-card" style={{marginTop:20}} aria-label="Contact an administrator">
    <h2 className="panel-title">Contact an administrator</h2>
    <p>Report a system failure, an account problem or something that is not working. Your message goes directly to the administrator you select.</p>
    {error&&<p className="auth-message" role="alert">{error}</p>}
    {sent&&<p className="auth-message success" role="status">Your support message was sent. Read replies and continue the conversation in <Link href="/dashboard/messages">Communications</Link>.</p>}
    {loading?<p role="status">Loading administrators...</p>:admins.length?<form className="flow-form" onSubmit={submit}>
      <label>Administrator<select name="administrator" required defaultValue={admins[0].id}>{admins.map(admin=><option key={admin.id} value={admin.id}>{admin.username}</option>)}</select></label>
      <label>Subject<input name="subject" required maxLength={190} placeholder="For example: I cannot open my dashboard"/></label>
      <label>What went wrong?<textarea name="body" rows={5} required maxLength={5000} placeholder="Describe the page, what you tried to do, and the error you saw."/></label>
      <p className="field-hint">Please keep passwords, verification codes and payment credentials out of your message.</p>
      <button className="button button-primary" disabled={busy}>{busy?'Sending...':'Send to administrator'}</button>
    </form>:<p>No active administrator is available for in-app messages. Use the support email below.</p>}
    <div className="flow-actions"><Link className="button button-secondary" href="/dashboard/messages">View conversations and replies</Link><a className="button button-secondary" href={emailLink}>Email support</a></div>
    <p className="field-hint">If in-app messaging fails, Email support opens your email app. Review and send the message there.</p>
  </section>;
}
