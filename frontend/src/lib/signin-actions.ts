import {createClient} from '@/lib/supabase/client';
import {authErrorMessage} from '@/lib/supabase/auth-errors';

export type SocialProvider = 'google' | 'github' | 'linkedin_oidc';

export async function startSocialSignIn(provider: SocialProvider, origin: string) {
  const {error} = await createClient().auth.signInWithOAuth({provider, options:{redirectTo:new URL('/auth/callback', origin).href}});
  if (error) throw new Error(authErrorMessage(error));
}

export async function sendMagicLink(email: string, origin: string) {
  const {error} = await createClient().auth.signInWithOtp({
    email:email.trim(), options:{shouldCreateUser:false, emailRedirectTo:new URL('/auth/callback', origin).href},
  });
  if (error) throw new Error(authErrorMessage(error));
}
