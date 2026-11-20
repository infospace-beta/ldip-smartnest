"use client";
import {useState} from 'react';
import {invitationGmail,invitationWhatsapp,invitationSms,localOnlyInvitation} from '@/lib/invitation-compose';
import Icon from '@/components/Icon';

export default function InvitationShare({link,email='',name='there'}:{link:string;email?:string;name?:string}) {
  const [copied,setCopied]=useState(false),[error,setError]=useState('');
  const ios=typeof navigator!=='undefined'&&/iPad|iPhone|iPod/.test(navigator.userAgent);
  let share:{email:string;whatsapp:string;sms:string;local:boolean};
  try {share={email:invitationGmail(email,name,link),whatsapp:invitationWhatsapp(name,link),sms:invitationSms(name,link,ios),local:localOnlyInvitation(link)};}
  catch {return <p role="alert">The invitation link is invalid. Create a new invitation.</p>;}
  return <div className="invitation-share">
    <div className="invite-link-controls"><input aria-label="Invitation link" readOnly value={link} onFocus={event=>event.currentTarget.select()}/><button className="button button-secondary button-compact" type="button" onClick={async()=>{setError('');try{await navigator.clipboard.writeText(link);setCopied(true);}catch{setError('Automatic copying is unavailable. Select and copy the link above.');}}}>{copied?'Copied':'Copy link'}</button></div>
    <div className="flow-actions" aria-label="Share invitation" style={{marginTop:12}}>
      <a className="button button-primary button-compact" href={share.email} target="_blank" rel="noopener noreferrer"><Icon name="message"/>Email via Gmail</a>
      <a className="button button-secondary button-compact" href={share.whatsapp} target="_blank" rel="noopener noreferrer"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M21 11.5a9 9 0 0 1-13.4 7.8L3 21l1.6-4.5A9 9 0 1 1 21 11.5Z"/><path d="M8 7c0 4 3 7 7 8l1-2-3-1-1 1-2-2 1-1-1-3Z"/></svg>WhatsApp</a>
      <a className="button button-secondary button-compact" href={share.sms}><Icon name="phone"/>SMS</a>
    </div>
    <p className="field-hint">Email opens Gmail with the recipient, subject and invitation link filled in. Review the draft and click Send. WhatsApp and SMS open drafts in their apps.</p>
    {share.local&&<p className="auth-message" role="note">This link uses localhost and works only on this computer. A public HTTPS site address is needed to share access with people on other devices.</p>}
    {copied&&<p role="status" className="form-message">Invitation link copied.</p>}{error&&<p role="alert" className="form-error">{error}</p>}
  </div>;
}
