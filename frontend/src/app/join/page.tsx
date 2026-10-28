"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import Icon from "@/components/Icon";
import { useAuth } from "@/contexts/AuthContext";
import { tenantInvitationsAPI } from "@/lib/api";

export default function JoinTenantPage() {
  const router = useRouter();
  const { login, register } = useAuth();
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [tenantName, setTenantName] = useState("");
  const [phone, setPhone] = useState("");
  const [loadingInvite, setLoadingInvite] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      const inviteToken = new URLSearchParams(window.location.search).get("token") ?? "";
      if (!inviteToken) {
        if (active) {
          setError("This invitation link is missing its invitation code.");
          setLoadingInvite(false);
        }
        return;
      }

      setToken(inviteToken);
      void tenantInvitationsAPI.details(inviteToken)
        .then(({ data }) => {
          if (!active) return;
          setEmail(data.email);
          setTenantName(data.tenant_name);
          setPhone(data.phone);
        })
        .catch(() => {
          if (active) setError("This invitation link is invalid, expired, or has already been used. Ask your manager for a new one.");
        })
        .finally(() => {
          if (active) setLoadingInvite(false);
        });
    });
    return () => { active = false; };
  }, []);

  const acceptInvitation = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const fullName = String(form.get("name") ?? "").trim();
    const password = String(form.get("password") ?? "");
    if (password !== String(form.get("confirmPassword") ?? "")) {
      setError("The passwords don’t match.");
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      await register({
        email,
        username: fullName.replace(/\s+/g, "."),
        password,
        role: "tenant",
        phone: String(form.get("phone") ?? "").trim(),
        consent: form.get("consent") === "on",
        invitation_token: token,
      });
      try {
        await login({ email, password });
        router.replace("/dashboard");
      } catch {
        setError("Invitation accepted. Your account is ready; please sign in with the password you just created.");
      }
    } catch {
      setError("We couldn’t accept this invitation. Confirm the email and try again, or ask your manager for a new link.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="auth-page">
      <div className="auth-layout join-layout">
        <aside className="auth-story">
          <Link className="brand" href="/">
            <span className="brand-mark">S</span>
            <span><span className="brand-name">SmartNest</span><span className="brand-caption">Property operations</span></span>
          </Link>
          <div className="auth-story-copy">
            <div className="page-eyebrow">Tenant portal</div>
            <h1>Your home, all in one place.</h1>
            <p>Accept your manager’s invitation to access your tenancy, payments, and maintenance requests.</p>
          </div>
          <div className="auth-foot">SmartNest · Tenant access</div>
        </aside>
        <section className="auth-content" aria-live="polite">
          <div className="page-eyebrow"><Icon name="home" />Tenant invitation</div>
          <h2>Join SmartNest</h2>
          {loadingInvite ? <div className="loading-state" role="status">Checking your invitation…</div> : error && !email ? (
            <div className="auth-message" role="alert">{error}<p><Link href="/login">Go to sign in</Link></p></div>
          ) : (
            <>
              <p className="auth-description">Create your login for {tenantName || "your tenant account"}.</p>
              {error && <div className="auth-message" role="alert">{error}</div>}
              <form className="auth-form" onSubmit={acceptInvitation}>
                <div className="field">
                  <label htmlFor="invite-name">Full name</label>
                  <input className="auth-input" id="invite-name" name="name" required maxLength={150} autoComplete="name" defaultValue={tenantName} />
                </div>
                <div className="field">
                  <label htmlFor="invite-email">Invited email</label>
                  <input className="auth-input" id="invite-email" type="email" value={email} readOnly />
                </div>
                <div className="field">
                  <label htmlFor="invite-phone">Phone number</label>
                  <input className="auth-input" id="invite-phone" name="phone" type="tel" maxLength={20} autoComplete="tel" defaultValue={phone} />
                </div>
                <div className="field">
                  <label htmlFor="invite-password">Create password</label>
                  <input className="auth-input" id="invite-password" name="password" type="password" required minLength={8} autoComplete="new-password" />
                </div>
                <div className="field">
                  <label htmlFor="invite-password-confirm">Confirm password</label>
                  <input className="auth-input" id="invite-password-confirm" name="confirmPassword" type="password" required minLength={8} autoComplete="new-password" />
                </div>
                <label className="consent-row">
                  <input name="consent" type="checkbox" required />
                  <span>I agree to SmartNest storing the account and contact details needed to manage my tenancy.</span>
                </label>
                <button className="button button-primary auth-submit" type="submit" disabled={submitting}>
                  {submitting ? "Joining…" : "Accept invitation"}
                </button>
              </form>
            </>
          )}
          <p className="auth-note">This one-time invitation expires seven days after it was created.</p>
        </section>
      </div>
    </main>
  );
}
