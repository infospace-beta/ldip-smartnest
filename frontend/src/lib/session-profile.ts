import { authAPI } from "@/lib/api";

// Password sign-in and the auth-state event can request the same profile together.
// Share only pending work; later calls must recheck current server permissions.
const pending = new Map<string, ReturnType<typeof authAPI.me>>();

export function loadSessionProfile(accessToken: string) {
  if (!accessToken.trim()) return Promise.reject(new Error("A sign-in session is required to load your profile."));
  const existing = pending.get(accessToken);
  if (existing) return existing;
  const request = authAPI.me(accessToken).finally(() => {
    if (pending.get(accessToken) === request) pending.delete(accessToken);
  });
  pending.set(accessToken, request);
  return request;
}
