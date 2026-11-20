export function invitationMessage(name: string, link: string) {
  return `Hello ${name},\n\nYou have been invited to SmartNest. Use this one-time link to register your account:\n\n${link}\n\nThis invitation is valid for seven days from its creation.\n\nThank you.`;
}

export type InvitationEmailProvider = "gmail" | "outlook" | "yahoo" | "default";

export function invitationEmailCompose(
  provider: InvitationEmailProvider,
  email: string,
  name: string,
  link: string,
) {
  const to = email.trim().toLowerCase();
  const subject = "Your SmartNest invitation";
  const body = invitationMessage(name, link);
  const params = new URLSearchParams({ to, body });
  if (provider === "gmail") {
    params.set("view", "cm");
    params.set("fs", "1");
    params.set("su", subject);
    return `https://mail.google.com/mail/?${params.toString()}`;
  }
  if (provider === "outlook") {
    params.set("subject", subject);
    return `https://outlook.office.com/mail/deeplink/compose?${params.toString()}`;
  }
  if (provider === "yahoo") {
    params.set("subject", subject);
    return `https://compose.mail.yahoo.com/?${params.toString()}`;
  }
  return `mailto:${encodeURIComponent(to)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

function internationalPhoneDigits(phone: string) {
  const normalized = phone.trim().replace(/[ ().-]/g, "");
  if (!/^\+?\d+$/.test(normalized)) return "";
  const digits = normalized.replace(/^\+/, "");
  return digits.length >= 7 && digits.length <= 15 && !digits.startsWith("0") ? digits : "";
}

export function invitationWhatsApp(phone: string, name: string, link: string) {
  const digits = internationalPhoneDigits(phone);
  const recipient = digits ? `/${digits}` : "/";
  return `https://wa.me${recipient}?text=${encodeURIComponent(invitationMessage(name, link))}`;
}
