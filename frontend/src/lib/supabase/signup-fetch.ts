// Keep the SDK's signup/PKCE handling, but send signup through our server to
// avoid a blocked browser cross-origin connection. Other requests are unchanged.
export function signupFetch(projectUrl: string, fetcher: typeof fetch = globalThis.fetch): typeof fetch {
  const project = new URL(projectUrl);
  return async (input, init) => {
    const target = new URL(input instanceof Request ? input.url : String(input));
    const method = init?.method ?? (input instanceof Request ? input.method : "GET");
    if (target.origin === project.origin && ["/auth/v1/signup", "/auth/v1/recover", "/auth/v1/otp", "/auth/v1/resend"].includes(target.pathname) && method.toUpperCase() === "POST") {
      const request = new Request(input, init);
      return fetcher(`/api/auth/${target.pathname.split("/").pop()}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: await request.text(),
        signal: request.signal,
        credentials: "same-origin",
        cache: "no-store",
      });
    }
    return fetcher(input, init);
  };
}
