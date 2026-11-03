export function invitationMailto(email: string, name: string, link: string) {
  const subject = "Your SmartNest invitation";
  const body = `Hello ${name},\n\nYou have been invited to SmartNest. Use this one-time link to register your account:\n\n${link}\n\nThis invitation is valid for seven days from its creation.\n\nThank you.`;
  return `mailto:${encodeURIComponent(email.trim().toLowerCase())}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}
