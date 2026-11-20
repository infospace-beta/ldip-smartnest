"use client";
import {useEffect, useState} from "react";
import {useRouter} from "next/navigation";
import {createClient} from "@/lib/supabase/client";
import {authErrorMessage} from "@/lib/supabase/auth-errors";
import Icon from "@/components/Icon";
import ProviderLogo from "@/components/ProviderLogo";
import {startSocialSignIn, type SocialProvider} from "@/lib/signin-actions";

export interface AuthCapabilities {google: boolean; github: boolean; linkedin: boolean; phone: boolean; passkeys: boolean; email: boolean;}
export function useAuthCapabilities() {
  const [settings, setSettings] = useState<AuthCapabilities | null>(null);
  useEffect(() => {let active = true; void fetch('/api/auth/capabilities').then(r => {if (!r.ok) throw Error(); return r.json();}).then(data => {if (active) setSettings(data);}).catch(() => {}); return () => {active = false;};}, []);
  return settings;
}

export default function SignInOptions() {
  const capabilities = useAuthCapabilities(), router = useRouter();
  const [sms, setSms] = useState(false), [sent, setSent] = useState(false);
  const [phone, setPhone] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<void>) => {setBusy(true); setError(''); try {await fn();} catch (e) {setError(e instanceof Error ? authErrorMessage(e) : 'Could not sign in.');} finally {setBusy(false);}};
  return <section className="signin-providers" aria-label="Sign-in options">
    <button type="button" className="button google-signin" disabled={busy || !capabilities?.google} title={capabilities && !capabilities.google ? 'Google sign-in is awaiting activation' : undefined} onClick={() => void run(() => startSocialSignIn('google', location.origin))}>
      <ProviderLogo provider="google"/>Continue with Google
    </button>
    <div className="signin-social-row">
      {([{provider:'linkedin_oidc', label:'LinkedIn', enabled:capabilities?.linkedin}, {provider:'github', label:'GitHub', enabled:capabilities?.github}] as {provider:SocialProvider;label:string;enabled:boolean|undefined}[]).map(item => <button key={item.provider} type="button" className="button social-signin" disabled={busy || !item.enabled} title={item.enabled ? undefined : `${item.label} sign-in is awaiting activation`} onClick={() => void run(() => startSocialSignIn(item.provider, location.origin))}><ProviderLogo provider={item.provider}/>{item.label}</button>)}
    </div>
    {capabilities && (!capabilities.google || !capabilities.github || !capabilities.linkedin) && <p className="signin-provider-note">Unavailable sign-in providers are awaiting activation.</p>}
    {error && <p role="alert" className="auth-message">{error}</p>}
    {capabilities?.phone && <button type="button" className="signin-text-button" onClick={() => {setSms(!sms); setError('');}}><Icon name="phone"/> {sms ? 'Use email and password' : 'Use an SMS code'}</button>}
    {sms && <form className="auth-form sms-signin" onSubmit={e => {e.preventDefault(); const form = e.currentTarget; void run(async () => {
      if (!sent) {const {error} = await createClient().auth.signInWithOtp({phone, options: {shouldCreateUser: false}}); if (error) throw error; setSent(true);}
      else {const {error} = await createClient().auth.verifyOtp({phone, token: String(new FormData(form).get('code')), type: 'sms'}); if (error) throw error; router.replace('/dashboard'); router.refresh();}
    });}}>
      <label htmlFor="sms-phone">Verified phone number</label><input id="sms-phone" type="tel" required pattern="\+[1-9][0-9]{7,14}" placeholder="+254712345678" autoComplete="tel" value={phone} onChange={e => {setPhone(e.target.value); setSent(false);}}/>
      {sent && <><p role="status">If this phone is linked to an account, a code has been requested.</p><label htmlFor="sms-code">SMS code</label><input id="sms-code" name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" required/></>}
      <button className="button button-secondary" disabled={busy}>{busy ? 'Please wait…' : sent ? 'Verify and sign in' : 'Send SMS code'}</button>
    </form>}
  </section>;
}
