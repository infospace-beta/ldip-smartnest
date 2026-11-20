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
}
