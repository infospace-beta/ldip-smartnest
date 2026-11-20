"use client";
import {Suspense,useState,type FormEvent} from 'react';
import Link from 'next/link';
import {useSearchParams} from 'next/navigation';

function ConfirmationForm() {
  const params=useSearchParams(),hash=params.get('token_hash')||'';
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[confirmed,setConfirmed]=useState(false);
  // Reinitialize the browser auth client from the session cookies set by the server.
  const continueToWorkspace=()=>{
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign('/dashboard');
  };
  const submit=async(event:FormEvent<HTMLFormElement>)=>{
    event.preventDefault();setBusy(true);setError('');
    const form=new FormData(event.currentTarget);
    try {
      const response=await fetch('/api/auth/confirm',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',cache:'no-store',
        body:JSON.stringify(hash?{token_hash:hash}:{email:form.get('email'),token:form.get('token')}),signal:AbortSignal.timeout(20000)});
      const result=await response.json();
      if(!response.ok||result.confirmed!==true)throw Error(result.message||'Email confirmation could not be completed.');
      window.history.replaceState(null,'','/auth/confirm');setConfirmed(true);
    }catch(e){setError(e instanceof Error?e.message:'Could not reach the confirmation service. Please try again.');}
    finally{setBusy(false);}
  };
  return <main className="auth-page"><section className="auth-content" style={{maxWidth:560,margin:'40px auto'}}>
    <Link className="brand" href="/"><span className="brand-mark">S</span><span className="brand-name">SmartNest</span></Link>
    <h1>{confirmed?'Email confirmed':'Confirm your email'}</h1>
    {confirmed?<><p role="status">Your email is verified. Continue to SmartNest. If your workspace is not linked yet, reopen your original invitation and choose “Sign in to accept”.</p><button type="button" className="button button-primary" onClick={continueToWorkspace}>Continue to SmartNest</button></>:<>
      <p>{hash?'Press Confirm to verify the email used for your SmartNest invitation. Opening this page alone does not use your link.':'Enter the email address and confirmation code from your latest SmartNest email. You can read the code on your phone and enter it here.'}</p>
      {error&&<p className="auth-message" role="alert">{error}</p>}
      <form className="auth-form" onSubmit={submit}>
        {!hash&&<><div className="field"><label htmlFor="confirm-email">Email address</label><input className="auth-input" id="confirm-email" name="email" type="email" autoComplete="username" maxLength={254} required/></div><div className="field"><label htmlFor="confirm-code">Confirmation code</label><input className="auth-input" id="confirm-code" name="token" inputMode="numeric" pattern="[0-9]{6,10}" autoComplete="one-time-code" required/></div></>}
        <button className="button button-primary" disabled={busy}>{busy?'Confirming...':'Confirm email'}</button>
      </form>
      <p>Use only the newest email. Confirmation links and codes expire and can be used once. If you need another, reopen your invitation and select Resend confirmation email.</p>
      <p>Already confirmed before? <Link href="/login">Sign in</Link>, or reopen your invitation to accept it using your existing password.</p>
    </>}
  </section></main>;
}
export default function ConfirmEmailPage(){return <Suspense fallback={<main role="status">Loading confirmation...</main>}><ConfirmationForm/></Suspense>;}
