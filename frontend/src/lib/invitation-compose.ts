export function invitationMessage(name: string, link: string) {
  const url = new URL(link);
  if (
    !['http:', 'https:'].includes(url.protocol) || url.username || url.password ||
    !['/join', '/join-account'].includes(url.pathname) || !url.searchParams.get('token')
  ) throw new Error('This invitation link is invalid.');
  return `Hello ${name || 'there'},\n\nYou have been invited to SmartNest. Open this one-time link to create your account or sign in to accept:\n\n${url.href}\n\nUse the invited email address. This invitation expires seven days after creation. Do not forward it to someone else.`;
}

export type InvitationEmailProvider = 'gmail' | 'outlook' | 'yahoo' | 'default';

export function invitationEmailCompose(provider: InvitationEmailProvider, email: string, name: string, link: string) {
  const address = email.trim().toLowerCase();
  if (address && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(address)) throw new Error('Enter a valid recipient email.');
  const subject = 'Your SmartNest invitation';
  const body = invitationMessage(name, link);
  if (provider === 'default') {
    return `mailto:${encodeURIComponent(address)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  }
  const origins = {
    gmail: 'https://mail.google.com/mail/',
    outlook: 'https://outlook.office.com/mail/deeplink/compose',
    yahoo: 'https://compose.mail.yahoo.com/',
  };
  const draft = new URL(origins[provider]);
  draft.searchParams.set('to', address);
  draft.searchParams.set('body', body);
  if (provider === 'gmail') {
    draft.searchParams.set('view', 'cm');
    draft.searchParams.set('fs', '1');
    draft.searchParams.set('su', subject);
  } else {
    draft.searchParams.set('subject', subject);
  }
  return draft.href;
}

export function invitationGmail(email: string, name: string, link: string) {
  return invitationEmailCompose('gmail', email, name, link);
}

function internationalPhoneDigits(phone: string) {
  const normalized = phone.trim().replace(/[ ().-]/g, '');
  if (!/^\+?\d+$/.test(normalized)) return '';
  const digits = normalized.replace(/^\+/, '');
  return digits.length >= 7 && digits.length <= 15 && !digits.startsWith('0') ? digits : '';
}

export function invitationWhatsApp(phone: string, name: string, link: string) {
  const digits = internationalPhoneDigits(phone);
  return `https://wa.me/${digits}?text=${encodeURIComponent(invitationMessage(name, link))}`;
}

export function invitationWhatsapp(name: string, link: string) {
  return invitationWhatsApp('', name, link);
}

export function invitationSms(name: string, link: string, ios = false) {
  return `sms:${ios ? '&' : '?'}body=${encodeURIComponent(invitationMessage(name, link))}`;
}

export function localOnlyInvitation(link: string) {
  return ['localhost', '127.0.0.1', '[::1]'].includes(new URL(link).hostname);
}
