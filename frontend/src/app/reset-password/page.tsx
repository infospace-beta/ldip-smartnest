"use client";

import PasswordInput from "@/components/PasswordInput";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";
import { authAPI } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";

function ResetPasswordFormPage() {
  const router = useRouter();
  const [validSession, setValidSession] = useState<boolean | null>(null);
  useEffect(() => {
    let active = true;
    void createClient().auth.getUser().then(({ data, error }) => {
      if (active) setValidSession(!error && !!data.user);
    }).catch(() => { if (active) setValidSession(false); });
    return () => { active = false; };
  }, []);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const newPassword = String(form.get("new_password1") ?? "");
    const confirmPassword = String(form.get("new_password2") ?? "");
    if (newPassword !== confirmPassword) {
      setError("The passwords don’t match.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await authAPI.confirmPasswordReset({
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
      router.replace("/login?password_changed=1");
    } catch {
      setError("This reset link is invalid or has expired. Request a new one and try again.");
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
            <h1>Choose a new password.</h1>
            <p>Use a unique password that you don’t use for another account.</p>
          </div>
          <div className="auth-foot">SmartNest Homes · Property operations, made clearer.</div>
        </aside>
        <section className="auth-content" aria-live="polite">
          <div className="page-eyebrow">Secure account recovery</div>
          <h2>Reset your password</h2>
          {validSession === null ? <div role="status">Checking your reset link…</div> : !validSession ? (
            <div className="auth-message" role="alert">This reset link is incomplete. <Link href="/forgot-password">Request another link</Link>.</div>
          ) : (
            <>
              <p className="auth-description">Create a new password for your SmartNest account.</p>
              {error && <div className="auth-message" role="alert">{error}</div>}
              <form className="auth-form" onSubmit={submit}>
                <div className="field">
                  <label htmlFor="reset-password">New password</label>
                  <PasswordInput className="auth-input" id="reset-password" name="new_password1" autoComplete="new-password" minLength={8} required />
                </div>
                <div className="field">
                  <label htmlFor="reset-password-confirm">Repeat new password</label>
                  <PasswordInput className="auth-input" id="reset-password-confirm" name="new_password2" autoComplete="new-password" minLength={8} required />
                </div>
                <button className="button button-primary auth-submit" type="submit" disabled={loading}>
                  {loading ? "Updating…" : "Update password"}
                </button>
              </form>
            </>
          )}
          <p className="auth-switch"><Link href="/login">Back to sign in</Link></p>
        </section>
      </div>
    </main>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<main className="auth-page"><div className="loading-state" role="status">Checking your reset link…</div></main>}>
      <ResetPasswordFormPage />
    </Suspense>
  );
}
