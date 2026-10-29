"use client";

import { Suspense, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { API_BASE_URL } from "@/lib/api";
import Icon from "@/components/Icon";

function messageFrom(error: unknown, fallback: string) {
  if (typeof error === "object" && error !== null && "response" in error) {
    const response = (error as { response?: { data?: unknown; status?: number } }).response;
    const data = response?.data;
    if (response?.status && response.status >= 500) {
      return `The SmartNest server returned an error (${response.status}). Check the Django backend terminal for details.`;
    }
    if (typeof data === "string") return data;
    if (typeof data === "object" && data !== null) {
      const values = Object.values(data as Record<string, unknown>).flatMap((value) =>
        Array.isArray(value) ? value : [value],
      );
      const message = values.find((value): value is string => typeof value === "string");
      if (message) return message;
    }
  }
  if (typeof error === "object" && error !== null) {
    const requestError = error as { code?: string; request?: unknown };
    if (requestError.code === "ERR_NETWORK" || requestError.request) {
      return `Cannot reach the SmartNest API at ${API_BASE_URL}. Start the Django backend and try again.`;
    }
  }
  return fallback;
}

function LoginFormPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login, register } = useAuth();
  const [creatingAccount, setCreatingAccount] = useState(searchParams.get("mode") === "register");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(
    searchParams.get("password_changed") === "1"
      ? "Your password has been updated. Sign in with your new password."
      : "",
  );

  const handleLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    setSuccess("");
    const form = new FormData(event.currentTarget);
    try {
      await login({
        email: String(form.get("email") ?? ""),
        password: String(form.get("password") ?? ""),
      });
      router.replace("/dashboard");
    } catch (requestError) {
      setError(messageFrom(requestError, "We couldn’t sign you in. Check your details and try again."));
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    setLoading(true);
    setError("");
    setSuccess("");
    const form = new FormData(event.currentTarget);
    const fullName = String(form.get("name") ?? "").trim();
    const password = String(form.get("new_password1") ?? "");
    if (password !== String(form.get("new_password2") ?? "")) {
      setError("The passwords don’t match.");
      setLoading(false);
      return;
    }

    try {
      await register({
        email: String(form.get("email") ?? ""),
        username: fullName.replace(/\s+/g, "."),
        password,
        role: "tenant",
        phone: String(form.get("phone") ?? ""),
        consent: form.get("consent") === "on",
      });
      formElement.reset();
      setCreatingAccount(false);
      setSuccess("Account created. Your manager must link your tenant record before you can sign in.");
    } catch (requestError) {
      setError(messageFrom(requestError, "We couldn’t create your account. Please try again."));
    } finally {
      setLoading(false);
    }
  };

  const switchMode = () => {
    setCreatingAccount((current) => !current);
    setError("");
    setSuccess("");
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
            <div className="page-eyebrow">A calmer way to manage homes</div>
            <h1>Good spaces. Better managed.</h1>
            <p>Bring the everyday work of property management into one clear, connected workspace.</p>
            <div className="auth-benefits">
              <div className="auth-benefit"><span className="metric-icon"><Icon name="properties" /></span>Know every home, unit and lease</div>
              <div className="auth-benefit"><span className="metric-icon"><Icon name="payments" /></span>Keep payments and records together</div>
              <div className="auth-benefit"><span className="metric-icon"><Icon name="maintenance" /></span>Move maintenance work forward</div>
            </div>
          </div>
          <div className="auth-foot">SmartNest Homes · Property operations, made clearer.</div>
        </aside>
        <section className="auth-content" aria-live="polite">
          <div className="page-eyebrow">{creatingAccount ? "Get started" : "Welcome back"}</div>
          <h2>{creatingAccount ? "Create your account" : "Sign in to SmartNest"}</h2>
          <p className="auth-description">
            {creatingAccount
              ? "Create a tenant account to access your SmartNest workspace."
              : "Use your account details to continue to your property workspace."}
          </p>
          {error && <div className="auth-message" role="alert">{error}</div>}
          {success && <div className="auth-message success" role="status">{success}</div>}
          <form className="auth-form" onSubmit={creatingAccount ? handleRegister : handleLogin}>
            {creatingAccount && (
              <>
                <div className="field">
                  <label htmlFor="account-name">Full name</label>
                  <input className="auth-input" id="account-name" name="name" autoComplete="name" maxLength={150} required placeholder="Your name" />
                </div>
                <div className="field">
                  <label htmlFor="account-phone">Phone number</label>
                  <input className="auth-input" id="account-phone" name="phone" type="tel" autoComplete="tel" maxLength={20} required placeholder="+254 7xx xxx xxx" />
                </div>
              </>
            )}
            <div className="field">
              <label htmlFor="account-email">Email address</label>
              <input className="auth-input" id="account-email" name="email" type="email" autoComplete="email" maxLength={254} required placeholder="you@example.com" />
            </div>
            <div className="field">
              <label htmlFor="account-password">Password</label>
              <input className="auth-input" id="account-password" name={creatingAccount ? "new_password1" : "password"} type="password" autoComplete={creatingAccount ? "new-password" : "current-password"} minLength={creatingAccount ? 8 : 1} required placeholder={creatingAccount ? "Create a strong password" : "Enter your password"} />
            </div>
            {creatingAccount && (
              <div className="field">
                <label htmlFor="account-confirm-password">Confirm password</label>
                <input className="auth-input" id="account-confirm-password" name="new_password2" type="password" autoComplete="new-password" minLength={8} required placeholder="Repeat your password" />
              </div>
            )}
            {creatingAccount && (
              <label className="consent-row">
                <input name="consent" type="checkbox" required />
                <span>I agree to SmartNest storing the account and contact details needed to manage my tenancy.</span>
              </label>
            )}
            <button className="button button-primary auth-submit" type="submit" disabled={loading}>
              {loading ? "Please wait…" : creatingAccount ? "Create account" : "Sign in"}
            </button>
          </form>
          {!creatingAccount && <Link className="forgot-password-link" href="/forgot-password">Forgot your password?</Link>}
          <div className="auth-switch">
            {creatingAccount ? "Already have an account? " : "New to SmartNest? "}
            <button type="button" onClick={switchMode}>{creatingAccount ? "Sign in" : "Create an account"}</button>
          </div>
          <p className="auth-note">Your sign-in and account details are verified by the SmartNest service.</p>
        </section>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<main className="auth-page"><div className="loading-state" role="status">Loading sign in…</div></main>}>
      <LoginFormPage />
    </Suspense>
  );
}
