// Supabase may deliberately obscure repeat signups for a confirmed identity.
// An empty identities list is a hint to offer sign-in, never proof of delivery.
export function signupOutcome(signup: {session: unknown; user?: {identities?: unknown[]} | null}) {
  return {
    requiresEmailConfirmation: !signup.session,
    mayAlreadyExist: !signup.session && Array.isArray(signup.user?.identities) && signup.user.identities.length === 0,
  };
}
