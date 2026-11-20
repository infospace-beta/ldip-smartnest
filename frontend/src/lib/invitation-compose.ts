<<<<<<< HEAD
export function invitationMessage(name:string,link:string) {
  const url=new URL(link);
  if(!['http:','https:'].includes(url.protocol)||url.username||url.password||!['/join','/join-account'].includes(url.pathname)||!url.searchParams.get('token'))throw new Error('This invitation link is invalid.');
  return `Hello ${name || 'there'},\n\nYou have been invited to SmartNest. Open this one-time link to create your account or sign in to accept:\n\n${url.href}\n\nUse the invited email address. This invitation expires seven days after creation. Do not forward it to someone else.`;
}
export function invitationGmail(email:string,name:string,link:string) {
  const address=email.trim().toLowerCase();
  if(address&&!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(address))throw new Error('Enter a valid recipient email.');
  const draft=new URL('https://mail.google.com/mail/');
  draft.searchParams.set('view','cm');
  draft.searchParams.set('fs','1');
  draft.searchParams.set('to',address);
  draft.searchParams.set('su','Your SmartNest invitation');
  draft.searchParams.set('body',invitationMessage(name,link));
  return draft.href;
}
export function invitationWhatsapp(name:string,link:string) {
  return `https://wa.me/?text=${encodeURIComponent(invitationMessage(name,link))}`;
}
export function invitationSms(name:string,link:string,ios=false) {
  return `sms:${ios?'&':'?'}body=${encodeURIComponent(invitationMessage(name,link))}`;
}
export function localOnlyInvitation(link:string) {
  return ['localhost','127.0.0.1','[::1]'].includes(new URL(link).hostname);
=======
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
>>>>>>> 21a14bdc76b11a75d3ba298f4d8e78966aa7d44d
}
