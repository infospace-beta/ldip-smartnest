"use client";
import {useEffect,useState} from 'react';
import {useRouter} from 'next/navigation';
import {createClient} from '@/lib/supabase/client';
import {authErrorMessage} from '@/lib/supabase/auth-errors';
import {ErrorBox} from '@/components/WorkflowShared';
export interface AuthCapabilities {google:boolean;phone:boolean;passkeys:boolean;email:boolean;}
export function useAuthCapabilities(){const [settings,setSettings]=useState<AuthCapabilities|null>(null);useEffect(()=>{let active=true;void fetch('/api/auth/capabilities').then(r=>{if(!r.ok)throw Error();return r.json();}).then(d=>{if(active)setSettings(d);}).catch(()=>{});return()=>{active=false;};},[]);return settings;}
export default function SignInOptions(){
  const capabilities=useAuthCapabilities(),router=useRouter();const [mode,setMode]=useState('magic'),[sent,setSent]=useState(false),[email,setEmail]=useState(''),[phone,setPhone]=useState(''),[error,setError]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
  const run=async(fn:()=>Promise<void>)=>{setBusy(true);setError('');setMessage('');try{await fn();}catch(e){setError(e instanceof Error?authErrorMessage(e):'Could not complete sign-in.');}finally{setBusy(false);}};
  return <section className="auth-alternatives"><h3>Other ways to sign in</h3><ErrorBox message={error}/>{message&&<p role="status">{message}</p>}
    <button className="button button-secondary" disabled={busy||!capabilities?.google} onClick={()=>void run(async()=>{const {error}=await createClient().auth.signInWithOAuth({provider:'google',options:{redirectTo:`${location.origin}/auth/callback`}});if(error)throw error;})}>Continue with Google{capabilities&&!capabilities.google?' — unavailable':''}</button>
    <button className="button button-secondary" disabled={busy||!capabilities?.passkeys} onClick={()=>void run(async()=>{const {error}=await createClient().auth.signInWithPasskey();if(error)throw error;router.replace('/dashboard');router.refresh();})}>Sign in with a passkey{capabilities&&!capabilities.passkeys?' — unavailable':''}</button>
    <form className="flow-form" onSubmit={e=>{e.preventDefault();void run(async()=>{const auth=createClient().auth;if(sent&&mode!=='magic'){const token=String(new FormData(e.currentTarget).get('token')||'');const {error}=mode==='phone'?await auth.verifyOtp({phone,token,type:'sms'}):await auth.verifyOtp({email,token,type:'email'});if(error)throw error;router.replace('/dashboard');router.refresh();}else{const {error}=mode==='phone'?await auth.signInWithOtp({phone,options:{shouldCreateUser:false}}):await auth.signInWithOtp({email,options:{shouldCreateUser:false,emailRedirectTo:`${location.origin}/auth/callback`}});if(error)throw error;setSent(true);setMessage(mode==='magic'?'If this address has an account, check your email for a sign-in link.':'If this account is eligible, a one-time code has been requested. Check your messages.');}});}}>
      <label>Sign-in method<select value={mode} onChange={e=>{setMode(e.target.value);setSent(false);setMessage('');}}><option value="magic">Email magic link</option><option value="email">Email one-time code</option><option value="phone" disabled={!capabilities?.phone}>Phone one-time code{capabilities&&!capabilities.phone?' — unavailable':''}</option></select></label>
      {mode==='phone'?<label>Phone number<input type="tel" required value={phone} onChange={e=>setPhone(e.target.value)} placeholder="+254…" autoComplete="tel"/></label>:<label>Email address<input type="email" required value={email} onChange={e=>setEmail(e.target.value)} autoComplete="email"/></label>}
      {sent&&mode!=='magic'&&<label>One-time code<input name="token" autoComplete="one-time-code" inputMode="numeric" pattern="[0-9]{6,10}" required/></label>}
      <button className="button button-secondary" disabled={busy||(mode==='phone'?!capabilities?.phone:!capabilities?.email)}>{busy?'Please wait…':sent&&mode!=='magic'?'Verify code':mode==='magic'?'Email a sign-in link':'Send one-time code'}</button>
      {sent&&mode!=='magic'&&<button type="button" className="button button-secondary" onClick={()=>setSent(false)}>Request a new code</button>}
    </form><p className="flow-muted">Use the account email or phone associated with your invitation. Available methods depend on your property’s sign-in service.</p>
  </section>;
}
