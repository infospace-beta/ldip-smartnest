import { sessionCookieSecurity } from "@/lib/supabase/cookie-security";
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { supabaseConfig } from "./config";

export async function createClient() {
  const store = await cookies();
  const { url, key } = supabaseConfig();
  return createServerClient(url, key, {
    cookies: {
      getAll: () => store.getAll(),
      setAll(values) {
        try {
          values.forEach(({ name, value, options }) => store.set(name, value, {...options,...sessionCookieSecurity(), expires:undefined, maxAge:!value?0:store.get('sn-trusted')?.value==='1'?604800:undefined}));
        } catch {
          // Server Components cannot write cookies; proxy refreshes the session.
        }
      },
    },
  });
}
