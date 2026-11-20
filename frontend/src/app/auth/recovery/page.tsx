"use client";
import {Suspense,useState,type FormEvent} from 'react';
import Link from 'next/link';
import {useSearchParams} from 'next/navigation';

function RecoveryForm() {
  const params=useSearchParams(),hash=params.get('token_hash')||'';
  const [busy,setBusy]=useState(false),[error,setError]=useState(params.get('error')?'This reset link is incomplete, expired, or already used. Request a new reset email, or enter the code from your newest email below.':'');
  const submit=async(event:FormEvent<HTMLFormElement>)=>{
    event.preventDefault();setBusy(true);setError('');
    const form=new FormData(event.currentTarget);
    try{
      const response=await fetch('/api/auth/recovery',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',cache:'no-store',
        body:JSON.stringify(hash?{token_hash:hash}:{email:form.get('email'),token:form.get('token')}),signal:AbortSignal.timeout(20000)});
      const result=await response.json();
      if(!response.ok||result.verified!==true)throw Error(result.message||'Could not verify this reset request.');
      window.history.replaceState(null,'','/auth/recovery');
      // Load the reset form with the server-established session cookies.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign('/reset-password');
    }catch(e){setError(e instanceof Error?e.message:'Could not reach the reset service. Try again shortly.');}
    finally{setBusy(false);}
  };
  return <main className="auth-page"><section className="auth-content" style={{maxWidth:560,margin:'40px auto'}}>
    <Link className="brand" href="/"><span className="brand-mark">S</span><span className="brand-name">SmartNest</span></Link>
    <h1>Reset your password</h1>
    <p>{hash?'Press Continue to verify this reset request and choose a new password. Opening this page alone does not use the link.':'Enter your email address and the reset code from your newest password-reset email. You can read the code on another device and enter it here.'}</p>
    {error&&<p className="auth-message" role="alert">{error}</p>}
    <form className="auth-form" onSubmit={submit}>
      {!hash&&<><div className="field"><label htmlFor="recovery-email">Email address</label><input className="auth-input" id="recovery-email" name="email" type="email" autoComplete="username" maxLength={254} required/></div><div className="field"><label htmlFor="recovery-code">Password-reset code</label><input className="auth-input" id="recovery-code" name="token" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6,10}" required/></div></>}
      <button className="button button-primary" disabled={busy}>{busy?'Checking reset request...':'Continue to choose password'}</button>
    </form>
    <p>Use only the newest reset email. Once a link or code has been used, it cannot be reused, even if the password change did not finish.</p>
    <p><Link href="/forgot-password">Request a new reset email</Link></p>
    <p>Already opened the link successfully? <Link href="/reset-password">Continue with your current reset session</Link>.</p>
  </section></main>;
}
export default function RecoveryPage(){return <Suspense fallback={<main role="status">Loading password recovery...</main>}><RecoveryForm/></Suspense>;}
