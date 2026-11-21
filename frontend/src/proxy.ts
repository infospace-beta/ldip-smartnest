import { sessionCookieSecurity } from "@/lib/supabase/cookie-security";
import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { supabaseConfig } from "@/lib/supabase/config";
import { authRequestOrigin } from "@/lib/public-site";

export async function proxy(request: NextRequest) {
  const { url, key } = supabaseConfig();
  let response = NextResponse.next({ request });
  const supabase = createServerClient(url, key, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll(values, headers) {
        values.forEach(({ name, value }) => request.cookies.set(name, value));
        response = NextResponse.next({ request });
        values.forEach(({ name, value, options }) => response.cookies.set(name, value, {...options,...sessionCookieSecurity(request.nextUrl.protocol === 'https:'),expires:undefined,maxAge:!value?0:request.cookies.get('sn-trusted')?.value==='1'?604800:undefined}));
        Object.entries(headers ?? {}).forEach(([name, value]) => response.headers.set(name, value));
      },
    },
  });
  const { data, error } = await supabase.auth.getClaims();
  if ((error || !data?.claims) && request.nextUrl.pathname.startsWith("/dashboard")) {
    const target = new URL("/login", authRequestOrigin(request));
    target.searchParams.set("next", request.nextUrl.pathname + request.nextUrl.search);
    const redirect = NextResponse.redirect(target);
    response.cookies.getAll().forEach((cookie) => redirect.cookies.set(cookie));
    redirect.headers.set("Cache-Control", "private, no-store");
    return redirect;
  }
  response.headers.set("Cache-Control", "private, no-store");
  return response;
}

export const config = {
  matcher: ["/dashboard/:path*", "/login", "/join", "/forgot-password", "/reset-password", "/auth/:path*", "/security", "/join-account"],
};
