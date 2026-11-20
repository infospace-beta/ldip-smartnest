"use client";
import {Suspense, useState, type FormEvent} from "react";
import Link from "next/link";
import {useRouter, useSearchParams} from "next/navigation";
import {useAuth} from "@/contexts/AuthContext";
import {getApiErrorMessage} from "@/lib/api";
import SignInOptions from "@/components/SignInOptions";
import PasswordInput from "@/components/PasswordInput";
import Icon from "@/components/Icon";
import {sendMagicLink} from "@/lib/signin-actions";

function LoginFormPage() {
  const router = useRouter(), params = useSearchParams(), {login} = useAuth();
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [mode, setMode] = useState<'password'|'magic'>('password'), [message, setMessage] = useState('');
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setBusy(true); setError(''); setMessage('');
    const form = new FormData(event.currentTarget);
    document.cookie = `sn-trusted=${form.get('trusted') === 'on' ? '1' : '0'}; Path=/; SameSite=Lax${location.protocol === 'https:' ? '; Secure' : ''}${form.get('trusted') === 'on' ? '; Max-Age=604800' : ''}`;
    try {
      if (mode === 'magic') {
        await sendMagicLink(String(form.get('email')), location.origin);
        setMessage('If this email has an account, check your inbox for a sign-in link or code. Use only the newest email.');
        return;
      }
      await login({email: String(form.get('email')), password: String(form.get('password'))});
      const next = params.get('next');
      router.replace(next && /^\/dashboard(?:[/?]|$)/.test(next) ? next : '/dashboard'); router.refresh();
    } catch (e) {setError(getApiErrorMessage(e, 'We could not sign you in. Check your details and try again.'));}
    finally {setBusy(false);}
  };
  return <main className="signin-page">
    <aside className="signin-story">
      <Link className="brand" href="/"><span className="brand-mark">S</span><span className="brand-name">SmartNest</span></Link>
      <div><span className="page-eyebrow">A place for everything</span><h1>Good spaces.<br/>Better managed.</h1><p>Your homes, people and everyday property work, together in one clear workspace.</p>
        <div className="signin-story-feature"><Icon name="properties"/><span>Every property. Every detail.</span></div>
        <div className="signin-story-feature"><Icon name="payments"/><span>Payments and records, connected.</span></div>
        <div className="signin-story-feature"><Icon name="maintenance"/><span>A little less work. A lot more clarity.</span></div>
      </div><span className="signin-story-footer">Property operations, made clearer.</span>
    </aside>
    <section className="signin-main" aria-labelledby="signin-heading">
      <div className="signin-card"><Link className="signin-mobile-brand brand" href="/"><span className="brand-mark">S</span>SmartNest</Link>
        <span className="page-eyebrow">Welcome back</span><h2 id="signin-heading">Sign in to SmartNest</h2><p className="signin-description">Your workspace is ready when you are.</p>
        {params.get('password_changed') === '1' && <p className="auth-message success" role="status">Password updated. Sign in with your new password.</p>}
        {params.get('auth_error') === 'oauth' && <p className="auth-message" role="alert">Social sign-in could not be completed. Try again. If it keeps failing, contact your administrator to check the sign-in provider settings.</p>}
        {params.get('auth_error') === '1' && <p className="auth-message" role="alert">This link is invalid, expired, already used, or was opened in a different browser. If your email is already confirmed, sign in with your password. Otherwise reopen your invitation and request a new confirmation email.</p>}
        {error && <p role="alert" className="auth-message">{error}</p>}
        {message && <p className="auth-message success" role="status">{message}</p>}
        {mode === 'magic' && <p className="signin-invitation"><Link href="/auth/magic-link">Already have a sign-in code? Enter it here</Link></p>}
        <SignInOptions/>
        <div className="signin-divider"><span>or use your email</span></div>
        <form className="auth-form signin-password-form" onSubmit={submit}>
          <div className="field"><label htmlFor="account-email">Email address</label><input className="auth-input" id="account-email" name="email" type="email" autoComplete="username" maxLength={254} required placeholder="you@example.com"/></div>
          {mode === 'password' && (<div className="field"><div className="signin-password-label"><label htmlFor="account-password">Password</label><Link href="/forgot-password">Forgot password?</Link></div><PasswordInput className="auth-input" id="account-password" name="password" autoComplete="current-password" required placeholder="Enter your password"/></div>)}
          <label className="signin-remember"><input name="trusted" type="checkbox"/> Keep me signed in on this device</label>
          <button className="button button-primary" disabled={busy}><Icon name={mode === "magic" ? "message" : "login"}/>{busy ? (mode === "magic" ? "Sending link..." : "Signing in...") : mode === "magic" ? "Email me a sign-in link" : "Sign in"}</button>
        </form>
        <button className="signin-text-button signin-magic-toggle" type="button" disabled={busy} onClick={() => {setMode(mode === 'password' ? 'magic' : 'password'); setError(''); setMessage('');}}><Icon name={mode === 'password' ? 'message' : 'login'}/>{mode === 'password' ? 'Sign in with a magic link instead' : 'Sign in with a password instead'}</button>
        <p className="signin-invitation">New to SmartNest? <Link href="/get-started">Join with an invitation</Link></p>
        <p className="signin-security-note"><Icon name="settings"/> Once you’re in, add an authenticator and backup email in Settings.</p>
      </div>
    </section>
  </main>;
}
export default function LoginPage() {return <Suspense fallback={<main className="signin-page" role="status">Loading sign-in…</main>}><LoginFormPage/></Suspense>;}
