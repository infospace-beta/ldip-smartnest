import type {createClient} from '@/lib/supabase/client';

type AuthClient = ReturnType<typeof createClient>['auth'];

// The caller first verifies a current authenticator code. Clearing only the
// Django preference leaves provider MFA enrolled and still blocks AAL1 updates.
export async function disableAccountMfa(auth: Pick<AuthClient,'mfa'|'refreshSession'>, savePreference:()=>Promise<void>) {
  const listing=await auth.mfa.listFactors();
  if(listing.error)throw listing.error;
  // Save while AAL2 is still available; enrolled-factor removal follows only
  // after the backend authorizes the security preference change.
  await savePreference();
  for(const factor of listing.data.all){
    const result=await auth.mfa.unenroll({factorId:factor.id});
    if(result.error)throw new Error('Authenticator removal was not completed. Retry turning off two-step verification, or contact your administrator.');
  }
  const remaining=await auth.mfa.listFactors();
  if(remaining.error)throw remaining.error;
  if(remaining.data.all.some(factor=>factor.status==='verified'))throw new Error('A verified authenticator is still enrolled. Retry turning off two-step verification.');
  const refreshed=await auth.refreshSession();
  if(refreshed.error)throw new Error('Authenticators were removed. Sign out and sign in again to refresh your session.');
}
