"use client";

import { useRef, useState, type FormEvent } from "react";
import { getApiErrorMessage } from "@/lib/api";
import { invitationEmailCompose, invitationMessage, invitationWhatsApp, type InvitationEmailProvider } from "@/lib/invitation-compose";

export default function InvitationComposer({ name, defaultEmail = "", defaultPhone = "", prepare }: {
  name: string;
  defaultEmail?: string;
  defaultPhone?: string;
  prepare: (email: string) => Promise<string>;
}) {
  const [email, setEmail] = useState(defaultEmail);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [link, setLink] = useState("");
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState("");
  const [shareStatus, setShareStatus] = useState("");
  const [phone, setPhone] = useState(defaultPhone);
  const [emailProvider, setEmailProvider] = useState<InvitationEmailProvider | "">("");
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

  const whatsappLink = link ? invitationWhatsApp(phone, name, link) : "";

  const shareBySms = async () => {
    const message = invitationMessage(name, link);
    setShareStatus("");
    if (navigator.share) {
      try {
        await navigator.share({ title: "Your SmartNest invitation", text: message });
        return;
      } catch (shareError) {
        if (shareError instanceof DOMException && shareError.name === "AbortError") return;
      }
    }

    try {
      await navigator.clipboard.writeText(message);
      setShareStatus("Invitation message copied. Paste it into your messaging app and send it.");
    } catch {
      linkInput.current?.focus();
      linkInput.current?.select();
      setShareStatus("Sharing is unavailable in this browser. Copy the invitation link above and paste it into your SMS app.");
    }
  };

  return (
    <form className="invitation-composer" onSubmit={prepareLink}>
      <label className="field"><span>Recipient email</span><input type="email" required maxLength={254} autoComplete="email" value={email} disabled={busy || Boolean(link)} onChange={(event) => setEmail(event.target.value)} /></label>
      <p className="panel-description">Create the registration link for {name}, then open a sharing app with the invitation ready to send.</p>
      {!link && <div><button className="button button-primary" type="submit" disabled={busy}>{busy ? "Preparing…" : "Create invitation link"}</button></div>}
      {link && <div className="hint-card invite-link-card">
        <strong>Invitation link ready</strong>
        <div className="invite-link-controls">
          <input ref={linkInput} aria-label="Invitation link" readOnly value={link} onFocus={(event) => event.currentTarget.select()} />
          <button className="button button-primary button-compact" type="button" onClick={() => void copyLink()}>{copied ? "Copied" : "Copy link"}</button>
        </div>
        <small>This one-time link is valid for seven days from its creation.</small>
      </div>}
      {link && <>
        <label className="field"><span>Email service</span><select value={emailProvider} onChange={(event) => {
          const value = event.target.value;
          if (value === "") setEmailProvider("");
          else if (value === "gmail" || value === "outlook" || value === "yahoo" || value === "default") setEmailProvider(value);
        }}><option value="">Choose an email service</option><option value="gmail">Gmail</option><option value="outlook">Outlook</option><option value="yahoo">Yahoo Mail</option><option value="default">Other / default email app</option></select></label>
        <label className="field"><span>Recipient phone for WhatsApp (optional)</span><input type="tel" autoComplete="tel" value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="+254 7xx xxx xxx" /><small className="field-hint">Include the country code for a direct chat, for example +254 712 345 678. Without a valid number, WhatsApp lets you choose the recipient.</small></label>
        <div className="invitation-modes" role="group" aria-label="Invitation delivery method">
          {emailProvider
            ? <a className="button button-secondary" href={invitationEmailCompose(emailProvider, email, name, link)} target="_blank" rel="noopener noreferrer">Open email</a>
            : <button className="button button-secondary" type="button" disabled>Choose email service first</button>}
          <button className="button button-secondary" type="button" onClick={() => void shareBySms()}>SMS</button>
          <a className="button button-secondary" href={whatsappLink} target="_blank" rel="noopener noreferrer">WhatsApp</a>
        </div>
      </>}
      {copied && <p className="form-message" role="status">Invitation link copied.</p>}
      {copyError && <p className="form-error" role="alert">{copyError}</p>}
      {shareStatus && <p className="form-message" role="status">{shareStatus}</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
    </form>
  );
}
