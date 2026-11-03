import { createBrowserClient } from "@supabase/ssr";
import { supabaseConfig } from "./config";
import { signupFetch } from "./signup-fetch";

export function createClient() {
  const { url, key } = supabaseConfig();
  return createBrowserClient(url, key, { global: { fetch: signupFetch(url) } });
}
