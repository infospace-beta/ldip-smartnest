"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { authAPI } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [cooldown,setCooldown]=useState(0);
  useEffect(()=>{if(!cooldown)return;const timer=setTimeout(()=>setCooldown(value=>Math.max(0,value-1)),1000);return()=>clearTimeout(timer);},[cooldown]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    setMessage("");
    const form = new FormData(event.currentTarget);
    try {
      const { data } = await authAPI.requestPasswordReset(String(form.get("email") ?? ""));
      setMessage(data.message);setCooldown(60);
    } catch (error) {
      setError(error instanceof Error ? error.message : "We couldn’t send the request. Please try again in a few minutes.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="auth-page">
      <div className="auth-layout">
        <aside className="auth-story">
          <Link className="brand" href="/">
            <span className="brand-mark">S</span>
            <span><span className="brand-name">SmartNest</span><span className="brand-caption">Property operations</span></span>
          </Link>
          <div className="auth-story-copy">
            <div className="page-eyebrow">Account support</div>
            <h1>Get back to your workspace.</h1>
            <p>We’ll email a secure, time-limited link if the address belongs to an active account.</p>
          </div>
          <div className="auth-foot">SmartNest Homes · Property operations, made clearer.</div>
        </aside>
        <section className="auth-content" aria-live="polite">
          <div className="page-eyebrow">Password recovery</div>
          <h2>Forgot your password?</h2>
          <p className="auth-description">Enter the email address on your account and we’ll send reset instructions.</p>
          {error && <div className="auth-message" role="alert">{error}</div>}
          {message && <div className="auth-message success" role="status">{message}</div>}
          <form className="auth-form" onSubmit={submit}>
            <div className="field">
              <label htmlFor="reset-email">Email address</label>
              <input className="auth-input" id="reset-email" name="email" type="email" autoComplete="email" maxLength={254} required />
            </div>
            <button className="button button-primary auth-submit" type="submit" disabled={loading||cooldown>0}>
              {loading ? "Sending…" : cooldown ? `Wait ${cooldown}s before resending` : "Send reset link"}
            </button>
          </form>
          <p><Link href="/auth/recovery">Enter a code from your newest reset email</Link></p>
          <p className="auth-switch"><Link href="/login">Back to sign in</Link></p>
          <p className="auth-note">For your privacy, the same confirmation is shown whether or not an account uses that email.</p>
        </section>
      </div>
    </main>
  );
}
