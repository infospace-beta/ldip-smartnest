"use client";
import {useCallback, useEffect, useState} from 'react';
import Image from 'next/image';
import Link from 'next/link';
import {useRouter} from 'next/navigation';
import {useAuth} from '@/contexts/AuthContext';
import {createClient} from '@/lib/supabase/client';
import {authenticatorQrSource} from '@/lib/authenticator-qr';
import {disableAccountMfa} from '@/lib/disable-mfa';
import api, {getApiErrorMessage} from '@/lib/api';
import {useAuthCapabilities} from '@/components/SignInOptions';

interface SecuritySettings {mfa_enabled:boolean; secondary_email:string; secondary_email_verified:boolean; pending_secondary_email:string; sms_notifications:boolean; sms_available:boolean; email_available:boolean;}
interface Factor {id:string; friendly_name?:string; status:string;}

export default function AccountSecuritySettings({challengeOnly = false}: {challengeOnly?:boolean}) {
  const {user, refreshProfile} = useAuth(), capabilities = useAuthCapabilities(), router = useRouter();
  const [settings, setSettings] = useState<SecuritySettings | null>(null), [factors, setFactors] = useState<Factor[]>([]);
  const [factorId, setFactorId] = useState(''), [qr, setQr] = useState(''), [secret, setSecret] = useState('');
  const [error, setError] = useState(''), [message, setMessage] = useState(''), [busy, setBusy] = useState(false);
  const [phone, setPhone] = useState(''), [phoneSent, setPhoneSent] = useState(false);
  const load = useCallback(async () => {
    const [{data}, result] = await Promise.all([api.get<SecuritySettings>('/auth/security/'), createClient().auth.mfa.listFactors()]);
    if (result.error) throw result.error;
    setSettings(data); setFactors(result.data.totp.filter(f => f.status === 'verified'));
    setFactorId(current => result.data.totp.some(f=>f.id===current&&f.status==='verified') ? current : result.data.totp.find(f=>f.status==='verified')?.id || '');
  }, []);
  const userId = user?.id;
  useEffect(() => {if (!userId) return; const timer = window.setTimeout(() => {void load().catch(e => setError(getApiErrorMessage(e, 'Could not load security settings.')));}, 0); return () => window.clearTimeout(timer);}, [userId, load]);
  const action = async (data: Record<string, unknown>) => {const response = await api.post<SecuritySettings>('/auth/security/', data); setSettings(response.data); await refreshProfile();};
  const run = async (fn: () => Promise<void>) => {setBusy(true); setError(''); setMessage(''); try {await fn();} catch (e) {setError(getApiErrorMessage(e, 'Could not update account security.'));} finally {setBusy(false);}};
  if (!settings && !error) return <p role="status">Loading security settings…</p>;
  return <section aria-label="Account security settings">
    {error && <p className="auth-message" role="alert">{error}</p>}{message && <p className="auth-message success" role="status">{message}</p>}
    <div className="security-grid">
      <article className="panel account-security-panel"><h2>{challengeOnly ? 'Verify your authenticator' : 'Two-step verification'}</h2>
        <p>{challengeOnly ? 'You chose to protect your account with an authenticator. Enter a current code to continue.' : settings?.mfa_enabled ? 'On. You will be asked for an authenticator code after signing in.' : 'Optional for every account. Add an authenticator for extra protection whenever you’re ready.'}</p>
        {!challengeOnly && !factors.length && !qr && <button className="button button-primary" disabled={busy} onClick={() => void run(async () => {
          const auth = createClient().auth, existing = await auth.mfa.listFactors(); if (existing.error) throw existing.error;
          for (const old of existing.data.all.filter(f => f.factor_type === 'totp' && f.status === 'unverified')) {const {error} = await auth.mfa.unenroll({factorId: old.id}); if (error) throw error;}
          const {data, error} = await auth.mfa.enroll({factorType:'totp', friendlyName:'SmartNest authenticator', issuer:'SmartNest'}); if (error) throw error;
          setFactorId(data.id); setQr(data.totp.qr_code); setSecret(data.totp.secret);
        })}>Set up authenticator</button>}
        {qr && <><p>Scan this QR code in Google Authenticator, Microsoft Authenticator or another authenticator app.</p><Image unoptimized width={200} height={200} className="security-qr" src={authenticatorQrSource(qr)} alt="Scan to set up your SmartNest authenticator"/><details><summary>Enter a setup key instead</summary><code>{secret}</code></details></>}
        {!challengeOnly && factors.length > 0 && <p>Turning off two-step verification removes your enrolled authenticators. Someone who obtains your password could access your account without an authenticator code.</p>}
        {(factorId || factors.length > 0) && <form className="flow-form" onSubmit={e => {e.preventDefault(); const form = new FormData(e.currentTarget); void run(async () => {
          const {error} = await createClient().auth.mfa.challengeAndVerify({factorId, code:String(form.get('code'))}); if (error) throw error;
          if (!challengeOnly && form.get('operation') === 'disable') {await disableAccountMfa(createClient().auth,()=>action({action:'disable_mfa'})); setFactorId(''); setMessage('Two-step verification is off and your enrolled authenticators have been removed. Set up an authenticator again whenever you want to enable it.');}
          else if (!challengeOnly) {await action({action:'enable_mfa'}); setMessage('Two-step verification is on.');}
          setQr(''); setSecret(''); await load();
          if (challengeOnly) {await refreshProfile(); router.replace(new URLSearchParams(location.search).get('next') === '/reset-password' ? '/reset-password' : '/dashboard'); router.refresh();}
        });}}>
          {factors.length > 1 && <label>Authenticator<select value={factorId} onChange={e => setFactorId(e.target.value)}>{factors.map(f => <option key={f.id} value={f.id}>{f.friendly_name || 'Authenticator'}</option>)}</select></label>}
          <label>Authenticator code<input name="code" required inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code"/></label>
          {!challengeOnly && factors.length > 0 && <label>Action<select name="operation"><option value="verify">{settings?.mfa_enabled ? 'Keep enabled' : 'Enable two-step verification'}</option><option value="disable">Turn off and remove authenticators</option></select></label>}
          <button className="button button-primary" disabled={busy}>{busy ? 'Checking…' : challengeOnly ? 'Verify and open workspace' : factors.length > 0 ? 'Confirm security change' : 'Verify and enable'}</button>
        </form>}
      </article>
      {!challengeOnly && <>
        <article className="panel account-security-panel"><h2>Backup email</h2><p>Add a second email and verify it with a code. It is a recovery contact for administrator-assisted recovery; your sign-in email stays the same.</p>
          {settings?.secondary_email_verified && <p><strong>{settings.secondary_email}</strong> · Verified</p>}
          {!settings?.email_available && <p>Email delivery needs to be activated before a verification code can be sent.</p>}
          <form className="flow-form" onSubmit={e => {e.preventDefault(); const email = String(new FormData(e.currentTarget).get('email')); void run(async () => {await action({action:'request_secondary_email', email}); setMessage('A six-digit code was sent to your backup email. It expires in 10 minutes.');});}}>
            <label>Second email address<input type="email" name="email" required autoComplete="email" placeholder="backup@example.com"/></label><button className="button button-secondary" disabled={busy || !settings?.email_available}>Send verification code</button>
          </form>
          {settings?.pending_secondary_email && <form className="flow-form" onSubmit={e => {e.preventDefault(); const code = String(new FormData(e.currentTarget).get('code')); void run(async () => {await action({action:'confirm_secondary_email', code}); setMessage('Your backup email is verified.');});}}><label>Code sent to {settings.pending_secondary_email}<input name="code" required inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code"/></label><button className="button button-primary" disabled={busy}>Verify backup email</button></form>}
          {(settings?.secondary_email || settings?.pending_secondary_email) && <button className="button button-secondary" disabled={busy} onClick={() => void run(async () => {await action({action:'remove_secondary_email'}); setMessage('Backup email removed.');})}>Remove backup email</button>}
        </article>
        <article className="panel account-security-panel"><h2>Phone and SMS</h2><p>Verify a phone number for SMS sign-in. Property notifications are a separate opt-in and never contain private property or payment details.</p>
          {!capabilities?.phone ? <p>SMS sign-in is awaiting activation of the SMS provider.</p> : <form className="flow-form" onSubmit={e => {e.preventDefault(); const form = new FormData(e.currentTarget); void run(async () => {
            if (!phoneSent) {const {error} = await createClient().auth.updateUser({phone}); if (error) throw error; setPhoneSent(true); setMessage('Check your phone for a verification code.');}
            else {const {error} = await createClient().auth.verifyOtp({phone, token:String(form.get('code')), type:'phone_change'}); if (error) throw error; setPhoneSent(false); setMessage('Phone verified. You can use SMS sign-in.');}
          });}}><label>Phone number<input type="tel" required pattern="\+[1-9][0-9]{7,14}" placeholder="+254712345678" value={phone} onChange={e => {setPhone(e.target.value); setPhoneSent(false);}}/></label>{phoneSent && <label>SMS code<input name="code" required pattern="[0-9]{6}" maxLength={6} inputMode="numeric" autoComplete="one-time-code"/></label>}<button className="button button-secondary" disabled={busy}>{phoneSent ? 'Verify phone' : 'Send SMS code'}</button></form>}
          <p>Property SMS notifications: <strong>{settings?.sms_notifications ? 'On' : 'Off'}</strong></p>
          {!settings?.sms_available && <p>Notification delivery is awaiting provider setup.</p>}
          <button className="button button-secondary" disabled={busy || (!settings?.sms_available && !settings?.sms_notifications)} onClick={() => void run(async () => {await action({action:'sms_notifications', enabled:!settings?.sms_notifications}); setMessage('SMS notification preference saved.');})}>{settings?.sms_notifications ? 'Turn off SMS notifications' : 'Enable SMS notifications'}</button>
        </article>
      </>}
    </div>
    {challengeOnly && <p><Link href="/login">Back to sign in</Link></p>}
  </section>;
}
