"use client";
import Link from 'next/link';
import {useEffect,useState,type FormEvent} from 'react';
import {useRouter} from 'next/navigation';
import {useAuth} from '@/contexts/AuthContext';
import {accountInvitationsAPI,tenantInvitationsAPI,getApiErrorMessage} from '@/lib/api';
import PasswordInput from '@/components/PasswordInput';
import ConfirmationHelp from '@/components/ConfirmationHelp';

export default function AcceptInvitationPage({kind}:{kind:'account'|'tenant'}) {
  const router=useRouter(),{register,login,acceptInvitation}=useAuth();
  const [token,setToken]=useState(''),[email,setEmail]=useState(''),[name,setName]=useState(''),[phone,setPhone]=useState('');
  const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[confirmation,setConfirmation]=useState(false);
  const [mode,setMode]=useState<'signup'|'existing'>('signup');
  useEffect(()=>{let active=true;void Promise.resolve().then(async()=>{
    const code=new URLSearchParams(location.search).get('token')||'';
    if(!code)throw new Error('This invitation is missing its code. Ask the sender for a new link.');
    const response=kind==='account'?await accountInvitationsAPI.details(code):await tenantInvitationsAPI.details(code);
    if(!active)return;
    setToken(code);setEmail(response.data.email);setPhone(response.data.phone);
    setName('name' in response.data?response.data.name:response.data.tenant_name);
  }).catch(()=>{if(active)setError('This invitation is missing, expired or already used. Ask the sender for a new link, or sign in if you already accepted it.');}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[kind]);
  const existing=()=>{setMode('existing');setConfirmation(false);setError('');};
  const submit=async(event:FormEvent<HTMLFormElement>)=>{
    event.preventDefault();const form=new FormData(event.currentTarget),password=String(form.get('password')||'');
    if(mode==='signup'&&password!==String(form.get('confirmPassword')||'')){setError('The passwords do not match.');return;}
    setBusy(true);setError('');
    const invitation=kind==='account'?{account_invitation_token:token}:{invitation_token:token};
    try{
      if(mode==='existing')await acceptInvitation({email,password,consent:form.get('consent')==='on',...invitation});
      else{
        const result=await register({email,password,username:String(form.get('name')||name).trim().replace(/\s+/g,'.'),phone:String(form.get('phone')||''),role:'tenant',consent:form.get('consent')==='on',...invitation});
        if(result.mayAlreadyExist){existing();setError('This email may already be registered. Use your existing password to sign in and accept. Repeating signup does not reset that password or send a new confirmation email.');return;}
        if(result.requiresEmailConfirmation){setConfirmation(true);return;}
        await login({email,password});
      }
      router.replace('/dashboard');router.refresh();
    }catch(e){setError(getApiErrorMessage(e,'Could not accept the invitation. If you already registered this email, use your existing password to sign in and accept.'));}
    finally{setBusy(false);}
  };
  return <main className="auth-page"><div className="auth-layout join-layout"><aside className="auth-story"><Link className="brand" href="/"><span className="brand-mark">S</span><span className="brand-name">SmartNest</span></Link><div className="auth-story-copy"><div className="page-eyebrow">Your invitation</div><h1>Your workspace, ready for you.</h1><p>Use the invited email. Your approved invitation determines your workspace role.</p></div><div className="auth-foot">SmartNest · Invited access</div></aside>
    <section className="auth-content" aria-live="polite"><div className="page-eyebrow">{kind==='account'?'Account invitation':'Tenant invitation'}</div><h2>{mode==='existing'?'Sign in to accept':'Join SmartNest'}</h2>
      {error&&<p className="auth-message" role="alert">{error}</p>}
      {loading?<p role="status">Checking your invitation...</p>:!email?<Link href="/login">Go to sign in</Link>:confirmation?<><p className="auth-message success" role="status">Your signup request was received. Check the invited inbox for a confirmation email. If you already verified this email before, use Sign in to accept instead.</p><ConfirmationHelp email={email} onExisting={existing}/></>:<>
        <p className="auth-description">{mode==='existing'?'Use the password you already set for this email. This invitation does not reset that password.':`Create a sign-in for ${name||'your invited account'}, or use your existing account.`}</p>
        <button type="button" className="button button-secondary" style={{marginBottom:16}} disabled={busy} onClick={()=>{setMode(mode==='signup'?'existing':'signup');setError('');}}>{mode==='signup'?'Already registered? Sign in to accept':'I need to create an account'}</button>
        <form className="auth-form" onSubmit={submit}>
          {mode==='signup'&&<><div className="field"><label htmlFor="invite-name">Full name</label><input className="auth-input" id="invite-name" name="name" required defaultValue={name} maxLength={150} autoComplete="name"/></div><div className="field"><label htmlFor="invite-phone">Phone number</label><input className="auth-input" id="invite-phone" name="phone" type="tel" defaultValue={phone} maxLength={20} autoComplete="tel"/></div></>}
          <div className="field"><label htmlFor="invite-email">Invited email</label><input className="auth-input" id="invite-email" type="email" value={email} readOnly autoComplete="username"/></div>
          <div className="field"><label htmlFor="invite-password">{mode==='signup'?'Create password':'Existing password'}</label><PasswordInput className="auth-input" id="invite-password" name="password" required minLength={mode==='signup'?8:1} autoComplete={mode==='signup'?'new-password':'current-password'}/></div>
          {mode==='signup'&&<div className="field"><label htmlFor="invite-confirm">Confirm password</label><PasswordInput className="auth-input" id="invite-confirm" name="confirmPassword" required minLength={8} autoComplete="new-password"/></div>}
          <label className="consent-row"><input name="consent" type="checkbox" required/><span>I accept this invitation and have read the <Link href="/privacy" target="_blank">privacy notice</Link> and <Link href="/terms" target="_blank">terms of use</Link>.</span></label>
          <button className="button button-primary auth-submit" disabled={busy}>{busy?'Please wait...':mode==='existing'?'Sign in and accept invitation':'Create account and accept'}</button>
        </form>
        {mode==='existing'&&<p><Link href="/forgot-password">Forgot your existing password?</Link></p>}
        <details style={{marginTop:16}}><summary>Missing a confirmation email?</summary><ConfirmationHelp email={email} onExisting={existing}/></details>
      </>}
      <p className="auth-note">This one-time invitation expires seven days after creation.</p>
    </section></div></main>;
}
