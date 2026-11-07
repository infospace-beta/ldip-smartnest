export function sessionCookieSecurity(isHttps = false) {
  return { secure: process.env.NODE_ENV === "production" || isHttps, sameSite: "lax" as const, path: "/" };
}
