"use client";
import {Suspense,useState,type FormEvent} from 'react';
import Link from 'next/link';
import {useSearchParams} from 'next/navigation';

function MagicLinkForm() {
  const params=useSearchParams(),hash=params.get('token_hash')||'';
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const submit=async(event:FormEvent<HTMLFormElement>)=>{
    event.preventDefault();setBusy(true);setError('');
    const form=new FormData(event.currentTarget);
    try {
      const response=await fetch('/api/auth/magic-link',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',cache:'no-store',
        body:JSON.stringify(hash?{token_hash:hash}:{email:form.get('email'),token:form.get('token')}),signal:AbortSignal.timeout(20000)});
      const result=await response.json();
      if(!response.ok||result.verified!==true)throw Error(result.message||'Sign-in could not be completed.');
      window.history.replaceState(null,'','/auth/magic-link');
      // Reload with the server-established session before workspace authorization.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign('/dashboard');
    }catch(e){setError(e instanceof Error?e.message:'Could not reach the sign-in service. Try again shortly.');}
    finally{setBusy(false);}
  };
  return <main className="auth-page"><section className="auth-content" style={{maxWidth:560,margin:'40px auto'}}>
    <Link className="brand" href="/"><span className="brand-mark">S</span><span className="brand-name">SmartNest</span></Link>
    <h1>Sign in to SmartNest</h1>
    <p>{hash?'Press Continue to finish signing in. Opening this page alone does not use your magic link.':'Enter your email address and the sign-in code from your newest SmartNest email. You can read the code on another device and enter it here.'}</p>
    {error&&<p className="auth-message" role="alert">{error}</p>}
    <form className="auth-form" onSubmit={submit}>
      {!hash&&<><div className="field"><label htmlFor="magic-email">Email address</label><input className="auth-input" id="magic-email" name="email" type="email" autoComplete="username" maxLength={254} required/></div><div className="field"><label htmlFor="magic-code">Sign-in code</label><input className="auth-input" id="magic-code" name="token" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6,10}" maxLength={10} required/></div></>}
      <button className="button button-primary" disabled={busy}>{busy?'Signing in...':'Continue to SmartNest'}</button>
    </form>
    {hash&&<p><Link href="/auth/magic-link">Enter an emailed code instead</Link></p>}
    <p>Use only the newest email. Sign-in links and codes expire and can be used once. Only continue if you requested this sign-in.</p>
    <p><Link href="/login">Request a new magic link or sign in with a password</Link></p>
  </section></main>;
}
export default function MagicLinkPage(){return <Suspense fallback={<main role="status">Loading sign-in...</main>}><MagicLinkForm/></Suspense>;}
