import { test } from "node:test";
import assert from "node:assert/strict";
import { ReviewApi } from "./investigations-api.mjs";

test("default fetch binds global receiver and injected fetch wrapper avoids ReviewApi receiver", async () => {
  const previous = globalThis.fetch;
  try {
    globalThis.fetch = async function () {
      assert.equal(this, globalThis);
      return { ok: true, json: async () => ({ reviews: true, demo: true, jobs: false }) };
    };
    assert.equal(await new ReviewApi().available(), true);
  } finally { globalThis.fetch = previous; }
  const injected = new ReviewApi(async function () {
    assert.equal(this, undefined);
    return { ok: true, json: async () => ({ reviews: true, demo: true, jobs: false }) };
  });
  assert.equal(await injected.available(), true);
});

test("optional API detection hides absent, disabled and non-JSON backends", async () => {
  for (const status of [404, 503, 200]) {
    const api = new ReviewApi(async () => ({ status, ok: status === 200, json: async () => ({ error: "unavailable" }) }));
    assert.equal(await api.available(), false);
  }
  assert.equal(await new ReviewApi(async (url) => {
    assert.equal(url, "/api/capabilities");
    return { ok: true, json: async () => ({ reviews: true, demo: true, jobs: false }) };
  }).available(), true);
  assert.equal(await new ReviewApi(async () => { throw new Error("offline"); }).available(), false);
  for (const payload of [null, [], { reviews: "true", demo: true, jobs: false }, { reviews: true, demo: true }, { reviews: true, demo: false, jobs: false }]) {
    assert.equal(await new ReviewApi(async () => ({ ok: true, json: async () => payload })).available(), false);
  }
});

test("login and versioned review contract use explicit bearer, same origin and no ambient credentials", async () => {
  const calls = [];
  const api = new ReviewApi(async (url, options) => {
    calls.push({ url, options });
    if (url.endsWith("login")) return { ok: true, json: async () => ({ token: "memory-token", actor: { username: "analyst", role: "analyst" } }) };
    if (url.endsWith("logout")) return { ok: true, json: async () => ({ logged_out: true }) };
    return { ok: true, json: async () => ({ version: options.method === "PUT" ? 1 : 0, review: options.method === "PUT" ? { notes: "server only", bookmarked: false, status: "investigating" } : null }) };
  });
  await assert.rejects(api.review("TH-1", "india"), /Sign in/);
  await api.login("analyst", "dummy-test-password");
  assert.equal(api.token, "memory-token");
  await api.review("TH +1", "global");
  await api.review("TH +1", "global", { version: 0, review: { notes: "server only", bookmarked: false, status: "investigating" } });
  assert.equal(calls[1].url, "/api/reviews/TH%20%2B1?scope=global");
  assert.equal(calls[1].options.headers.Authorization, "Bearer memory-token");
  assert.equal(calls[2].options.method, "PUT");
  assert.equal(JSON.parse(calls[2].options.body).version, 0);
  for (const { options } of calls) { assert.equal(options.credentials, "omit"); assert.equal(options.redirect, "error"); }
  await api.logout(); assert.equal(api.token, null); assert.equal(api.actor, null);
});

test("conflicts retain session, unauthorized clears token, failed logout clears memory", async () => {
  let status = 409;
  const api = new ReviewApi(async () => ({ ok: false, status, json: async () => ({ error: "failure" }) }));
  api.token = "token"; api.actor = { username: "analyst" };
  await assert.rejects(api.review("TH-1", "india", { version: 0 }), /draft is retained/);
  assert.equal(api.token, "token");
  status = 401;
  await assert.rejects(api.review("TH-1", "india"), /401/);
  assert.equal(api.token, null);
  api.token = "token"; status = 503;
  await assert.rejects(api.logout(), /503/); assert.equal(api.token, null);
});
