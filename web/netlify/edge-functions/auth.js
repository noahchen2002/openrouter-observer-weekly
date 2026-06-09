// Password gate for the public dashboard (competitive data — must not be open).
// Uses HTTP Basic Auth: any username, password must equal the DASH_PASSWORD
// environment variable set on the Netlify site. If DASH_PASSWORD is unset the
// gate is open (fail-safe for first deploy), so always set it.
export default async (request, context) => {
  const expected = Netlify.env.get("DASH_PASSWORD");
  const expectedUser = Netlify.env.get("DASH_USER") || "";
  if (!expected) {
    return context.next();
  }
  const header = request.headers.get("authorization") || "";
  const [scheme, encoded] = header.split(" ");
  if (scheme === "Basic" && encoded) {
    let decoded = "";
    try {
      decoded = atob(encoded);
    } catch (_e) {
      decoded = "";
    }
    const idx = decoded.indexOf(":");
    const user = idx >= 0 ? decoded.slice(0, idx) : "";
    const pass = idx >= 0 ? decoded.slice(idx + 1) : "";
    if (pass === expected && (!expectedUser || user === expectedUser)) {
      return context.next();
    }
  }
  // NOTE: header values must be ASCII only — a non-ASCII realm makes the edge
  // runtime throw (500) and the browser never shows the password prompt.
  return new Response("Password required / 需要访问密码", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="OpenRouter Dashboard"' },
  });
};
