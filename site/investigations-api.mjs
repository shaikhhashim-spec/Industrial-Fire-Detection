/** Same-origin optional API. Session tokens stay in this module's memory only. */
export class ReviewApi {
  constructor(fetcher = globalThis.fetch.bind(globalThis)) { this.fetcher = (...args) => fetcher(...args); this.token = null; this.actor = null; }
  async available() {
    try {
      const response = await this.fetcher("/api/capabilities", { credentials: "omit", cache: "no-store", redirect: "error", signal: AbortSignal.timeout(5000) });
      const data = await response.json();
      return response.ok && data !== null && typeof data === "object" && !Array.isArray(data) &&
        data.reviews === true && data.demo === true && typeof data.jobs === "boolean";
    } catch { return false; }
  }
  async request(path, method = "GET", body) {
    const response = await this.fetcher(`/api${path}`, { method, credentials: "omit", cache: "no-store", redirect: "error",
      signal: AbortSignal.timeout(15000), headers: { "Content-Type": "application/json", ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    let data;
    try { data = await response.json(); } catch { throw new Error("Server returned an unsupported response"); }
    if (!response.ok) {
      if (response.status === 401) { this.token = null; this.actor = null; }
      const error = new Error(response.status === 409 ? "Server review changed. Your draft is retained; reload the server version before saving." : `Server request failed (${response.status}): ${typeof data.error === "string" ? data.error.slice(0, 300) : "unavailable"}`);
      error.status = response.status; throw error;
    }
    return data;
  }
  async login(username, password) {
    const data = await this.request("/auth/login", "POST", { username, password });
    if (!data || typeof data.token !== "string" || !data.token || data.token.length > 256 || !["admin", "analyst"].includes(data.actor?.role) || typeof data.actor?.username !== "string") throw new Error("Unsupported login response");
    this.token = data.token; this.actor = data.actor; return this.actor;
  }
  async logout() {
    try { await this.request("/auth/logout", "POST", {}); }
    finally { this.token = null; this.actor = null; }
  }
  async review(event, scope, body) {
    if (!this.token) throw new Error("Sign in to access server reviews");
    if (!["india", "global"].includes(scope)) throw new Error("Unsupported review scope");
    const data = await this.request(`/reviews/${encodeURIComponent(event)}?scope=${scope}`, body ? "PUT" : "GET", body);
    if (!data || !Number.isSafeInteger(data.version) || data.version < 0 ||
        data.review !== null && (!data.review || typeof data.review.notes !== "string" || data.review.notes.length > 16000 ||
        typeof data.review.bookmarked !== "boolean" || !["unreviewed", "investigating", "reviewed"].includes(data.review.status))) {
      throw new Error("Unsupported server review response");
    }
    return data;
  }
}
