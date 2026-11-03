import { supabaseConfig } from "@/lib/supabase/config";

const noStore = { "Cache-Control": "no-store" };

// Relay only signup to the configured project. Supabase still validates the
// credentials, sends confirmation email, and enforces its signup restrictions.
export async function POST(request: Request) {
  const origin = request.headers.get("origin");
  if (origin !== new URL(request.url).origin) {
    return Response.json({ code: "signup_origin_invalid", msg: "Open the signup form on this website and try again." }, { status: 403, headers: noStore });
  }
  if (!request.headers.get("content-type")?.includes("application/json")) {
    return Response.json({ msg: "Expected a JSON signup request." }, { status: 415, headers: noStore });
  }
  if (Number(request.headers.get("content-length")) > 16384) {
    return Response.json({ msg: "Signup request is too large." }, { status: 413, headers: noStore });
  }
  const body = await request.text();
  if (body.length > 16384) {
    return Response.json({ msg: "Signup request is too large." }, { status: 413, headers: noStore });
  }
  try {
    JSON.parse(body);
  } catch {
    return Response.json({ msg: "Invalid signup request." }, { status: 400, headers: noStore });
  }
  try {
    const { url, key } = supabaseConfig();
    const target = new URL("/auth/v1/signup", url);
    // Confirmation must return to this website, never to a submitted redirect.
    target.searchParams.set("redirect_to", new URL("/auth/callback", request.url).href);
    const upstream = await fetch(target, {
      method: "POST",
      headers: { apikey: key, Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(15000),
    });
    const headers = new Headers(noStore);
    headers.set("Content-Type", "application/json");
    for (const name of ["retry-after", "x-sb-error-code", "x-supabase-api-version"]) {
      const value = upstream.headers.get(name);
      if (value) headers.set(name, value);
    }
    return new Response(await upstream.text(), { status: upstream.status, headers });
  } catch {
    return Response.json({ code: "signup_service_unavailable", msg: "Account creation cannot reach the sign-in service. Please try again shortly." }, { status: 503, headers: noStore });
  }
}
