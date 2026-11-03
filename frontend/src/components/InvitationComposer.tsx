"use client";

import { useRef, useState, type FormEvent } from "react";
import { getApiErrorMessage } from "@/lib/api";

export default function InvitationComposer({ name, defaultEmail = "", prepare }: {
  name: string;
  defaultEmail?: string;
  prepare: (email: string) => Promise<string>;
}) {
  const [email, setEmail] = useState(defaultEmail);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [link, setLink] = useState("");
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState("");
  const linkInput = useRef<HTMLInputElement>(null);
  const inFlight = useRef(false);

  const prepareLink = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (inFlight.current || link) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      setLink(await prepare(email.trim().toLowerCase()));
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Could not prepare the invitation. Please try again."));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  const copyLink = async () => {
    setCopied(false);
    setCopyError("");
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
    } catch {
      linkInput.current?.focus();
      linkInput.current?.select();
      setCopyError("Select and copy the link above. Automatic copying is unavailable in this browser.");
    }
  };

  return (
    <form className="invitation-composer" onSubmit={prepareLink}>
      <label className="field"><span>Recipient email</span><input type="email" required maxLength={254} autoComplete="email" value={email} disabled={busy || Boolean(link)} onChange={(event) => setEmail(event.target.value)} /></label>
      <p className="panel-description">Create the registration link for {name}, then copy and share it. Sending by email, SMS, and WhatsApp is currently disabled.</p>
      {!link && <div><button className="button button-primary" type="submit" disabled={busy}>{busy ? "Preparing…" : "Create invitation link"}</button></div>}
      {link && <div className="hint-card invite-link-card">
        <strong>Invitation link ready</strong>
        <div className="invite-link-controls">
          <input ref={linkInput} aria-label="Invitation link" readOnly value={link} onFocus={(event) => event.currentTarget.select()} />
          <button className="button button-primary button-compact" type="button" onClick={() => void copyLink()}>{copied ? "Copied" : "Copy link"}</button>
        </div>
        <small>This one-time link is valid for seven days from its creation.</small>
      </div>}
      <div className="invitation-modes" role="group" aria-label="Invitation delivery method">
        <button className="button button-secondary" type="button" disabled>Send email</button>
        <button className="button button-secondary" type="button" disabled>SMS</button>
        <button className="button button-secondary" type="button" disabled>WhatsApp</button>
      </div>
      {copied && <p className="form-message" role="status">Invitation link copied.</p>}
      {copyError && <p className="form-error" role="alert">{copyError}</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
    </form>
  );
}
