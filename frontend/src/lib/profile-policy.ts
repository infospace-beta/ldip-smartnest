// Email verification flows use Supabase before entering a Django workspace.
// Workspace authorization resumes on the dashboard after session establishment.
export function shouldLoadWorkspaceProfile(pathname:string,event:string) {
  const path=pathname.replace(/\/+$/,'')||'/';
  return event!=='PASSWORD_RECOVERY' && !['/forgot-password','/reset-password','/auth/recovery','/auth/magic-link'].includes(path);
}
