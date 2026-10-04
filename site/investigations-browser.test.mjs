import { test } from "node:test";
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";

test("real browser capabilities network, login and optimistic server save", {
  skip: !process.env.INVESTIGATIONS_PLAYWRIGHT || !process.env.INVESTIGATIONS_LIVE_URL ||
    !process.env.INVESTIGATIONS_QA_USERNAME || !process.env.INVESTIGATIONS_QA_PASSWORD,
}, async () => {
  const { chromium } = await import(pathToFileURL(process.env.INVESTIGATIONS_PLAYWRIGHT));
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const page = await browser.newPage();
    const errors = []; page.on("pageerror", (e) => errors.push(e.message));
    // Verify current source against a real backend even when its assembled assets lag.
    await page.route("**/investigations-api.mjs", async (route) => route.fulfill({
      contentType: "text/javascript", body: await readFile(new URL("./investigations-api.mjs", import.meta.url), "utf8"),
    }));
    const capabilities = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/capabilities");
    await page.goto(process.env.INVESTIGATIONS_LIVE_URL);
    const response = await capabilities;
    assert.equal(response.status(), 200);
    assert.equal(response.headers()["www-authenticate"], undefined);
    assert.deepEqual(await response.json(), { reviews: true, demo: true, jobs: false });
    await page.locator(".case-row").first().click();
    await page.getByRole("tab", { name: "Review", exact: true }).click();
    await page.locator(".server-review summary").click();
    await page.locator(".server-review input[autocomplete=username]").fill(process.env.INVESTIGATIONS_QA_USERNAME);
    await page.locator(".server-review input[type=password]").fill(process.env.INVESTIGATIONS_QA_PASSWORD);
    const login = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/auth/login");
    await page.getByRole("button", { name: "Sign in to server", exact: true }).click();
    const loginResponse = await login; assert.equal(loginResponse.status(), 200);
    const session = await loginResponse.json();
    assert.equal(await page.evaluate((token) => [...Object.values(localStorage), ...Object.values(sessionStorage)].some((s) => s.includes(token)), session.token), false);
    const load = page.waitForResponse((r) => r.url().includes("/api/reviews/") && r.request().method() === "GET");
    await page.getByRole("button", { name: "Load server version", exact: true }).click();
    const baselineResponse = await load; assert.equal(baselineResponse.status(), 200);
    const baseline = await baselineResponse.json();
    await page.getByLabel("Server notes", { exact: true }).fill("Temporary real-browser QA annotation");
    await page.locator("#server-assessment").selectOption("industrial_heat");
    await page.locator("#server-supporting-sources").fill("https://example.org/qa-evidence");
    await page.locator("#server-uncertainty").fill("QA annotation, not independently verified evidence");
    const saved = page.waitForResponse((r) => r.url().includes("/api/reviews/") && r.request().method() === "PUT");
    await page.getByRole("button", { name: "Save temporary server review", exact: true }).click();
    const savedResponse = await saved; assert.equal(savedResponse.status(), 200);
    const result = await savedResponse.json();
    assert.equal(result.version, baseline.version + 1);
    assert.equal(result.review.notes, "Temporary real-browser QA annotation");
    assert.equal(result.review.assessment, "industrial_heat");
    assert.deepEqual(result.review.supportingSources, ["https://example.org/qa-evidence"]);
    assert.equal(result.review.status, baseline.review?.status ?? "unreviewed");
    await page.getByRole("button", { name: "Load server version", exact: true }).click();
    assert.equal(await page.locator("#server-assessment").inputValue(), "industrial_heat");
    // Restore the pre-test review through normal concurrency checks; audit records remain.
    const restored = await page.request.put(baselineResponse.url(), { headers: { Authorization: `Bearer ${session.token}` },
      data: { version: result.version, review: baseline.review ?? { notes: "", bookmarked: false, status: "unreviewed" } } });
    assert.equal(restored.status(), 200);
    const logout = page.waitForResponse((r) => r.url().endsWith("/api/auth/logout"));
    await page.getByRole("button", { name: "Sign out", exact: true }).click();
    assert.equal((await logout).status(), 200);
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

// Opt-in browser QA uses an external Playwright installation, serving owned source directly.
test("Investigations desktop/mobile, blocked storage and temporary server review", {
  skip: !process.env.INVESTIGATIONS_PLAYWRIGHT,
}, async () => {
  const server = createServer(async (request, response) => {
    try {
      const path = new URL(request.url, "http://localhost").pathname;
      const base = path.startsWith("/globe/data/") ? new URL("../holo-view-maker/public/data/", import.meta.url) : new URL("./", import.meta.url);
      const name = path.startsWith("/globe/data/") ? path.slice(12) : path.slice(1);
      if (!/^[a-zA-Z0-9_.-]+$/.test(name)) throw new Error("Invalid path");
      response.setHeader("Content-Type", name.endsWith(".mjs") || name.endsWith(".js") ? "text/javascript" : name.endsWith(".css") ? "text/css" : name.endsWith(".json") ? "application/json" : "text/html");
      response.end(await readFile(new URL(name, base)));
    } catch { response.writeHead(404); response.end("Not found"); }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const url = `http://127.0.0.1:${server.address().port}/investigations.html`;
  const { chromium } = await import(pathToFileURL(process.env.INVESTIGATIONS_PLAYWRIGHT));
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage(); const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.route("**/api/capabilities", (route) => route.fulfill({ json: { reviews: true, demo: true, jobs: false } }));
    await page.route("**/api/auth/login", (route) => route.fulfill({ json: { token: "test-memory-token", actor: { username: "qa-analyst", role: "analyst" } } }));
    let serverVersion = 0, serverReview = null;
    await page.route("**/api/reviews/**", async (route) => {
      if (route.request().method() === "GET") return route.fulfill({ json: { version: serverVersion, review: serverReview } });
      assert.equal(route.request().headers().authorization, "Bearer test-memory-token");
      const body = route.request().postDataJSON(); assert.equal(body.version, serverVersion);
      serverReview = body.review;
      serverVersion++; return route.fulfill({ json: { version: serverVersion, review: serverReview, actor: "qa-analyst", updated_at: 1791030000 } });
    });
    await page.goto(url);
    await page.locator(".case-row").first().waitFor();
    assert.equal(await page.locator(".case-row").count(), 50);
    await page.locator(".case-row").first().click();
    assert.match(await page.getByRole("link", { name: "Inspect 3D" }).getAttribute("href"), /globe\/\?region=india&event=.+&lat=.+&lon=.+&z=8/);
    await page.getByRole("tab", { name: "History", exact: true }).click();
    assert.match(await page.locator("#dossier-panel").textContent(), /supplied observations|history unavailable/i);
    await page.getByRole("tab", { name: "Screening", exact: true }).click();
    assert.match(await page.locator("#dossier-panel").textContent(), /no LLMs/);
    await page.getByRole("tab", { name: "Review", exact: true }).click();
    await page.locator("#review-notes").fill("=SUM(A1)\nLocal QA note <script>");
    await page.getByRole("button", { name: "Save local review", exact: true }).click();
    assert.match(await page.locator("#storage-status").textContent(), /Saved locally/);
    await page.locator(".server-review summary").click();
    await page.locator(".server-review input[autocomplete=username]").fill("qa-analyst");
    await page.locator(".server-review input[type=password]").fill("test-only");
    await page.getByRole("button", { name: "Sign in to server", exact: true }).click();
    await page.getByRole("button", { name: "Load server version", exact: true }).click();
    await page.getByLabel("Server notes", { exact: true }).fill("Temporary server QA");
    await page.locator("#server-assessment").selectOption("industrial_heat");
    await page.locator("#server-supporting-sources").fill("https://example.org/independent-report\nField visit report 123");
    await page.locator("#server-uncertainty").fill("Facility operation reported; exact source unresolved.");
    await page.getByRole("button", { name: "Save temporary server review", exact: true }).click();
    await page.waitForFunction(() => document.querySelector(".server-review").textContent.includes("Temporary server save: version 1"));
    assert.equal(serverReview.assessment, "industrial_heat");
    assert.equal(serverReview.status, "unreviewed");
    assert.deepEqual(serverReview.supportingSources, ["https://example.org/independent-report", "Field visit report 123"]);
    assert.equal(serverReview.uncertainty, "Facility operation reported; exact source unresolved.");
    assert.ok(Number.isFinite(Date.parse(serverReview.assessedAt)));
    const assessedAt = serverReview.assessedAt;
    await page.getByRole("button", { name: "Load server version", exact: true }).click();
    await page.waitForFunction(() => document.querySelector(".server-review").textContent.includes("Server version 1 loaded."));
    assert.equal(await page.locator("#server-assessment").inputValue(), "industrial_heat");
    assert.equal(await page.locator("#server-uncertainty").inputValue(), serverReview.uncertainty);
    // Workflow edits preserve evidence and assessment time; dirty reload preserves edits.
    await page.getByLabel("Server status", { exact: true }).selectOption("reviewed");
    await page.getByRole("button", { name: "Load server version", exact: true }).click();
    await page.waitForFunction(() => document.querySelector(".server-review").textContent.includes("your draft retained"));
    assert.equal(await page.getByLabel("Server status", { exact: true }).inputValue(), "reviewed");
    await page.getByRole("button", { name: "Save temporary server review", exact: true }).click();
    await page.waitForFunction(() => document.querySelector(".server-review").textContent.includes("Temporary server save: version 2"));
    assert.equal(serverReview.assessedAt, assessedAt);
    assert.equal(serverReview.assessment, "industrial_heat");
    assert.equal(await page.evaluate(() => Object.values(localStorage).some((s) => s.includes("test-memory-token"))), false);
    if (process.env.INVESTIGATIONS_SCREENSHOT) await page.screenshot({ path: process.env.INVESTIGATIONS_SCREENSHOT.replace(".png", "-desktop.png") });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.locator(".case-queue").isVisible(), false);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    if (process.env.INVESTIGATIONS_SCREENSHOT) await page.screenshot({ path: process.env.INVESTIGATIONS_SCREENSHOT });
    await page.getByRole("button", { name: "Back to queue" }).click();
    assert.equal(await page.locator(".case-queue").isVisible(), true);
    assert.deepEqual(errors, []);
    await context.close();

    const blocked = await browser.newContext({ viewport: { width: 390, height: 844 } });
    await blocked.addInitScript(() => { Storage.prototype.setItem = () => { throw new Error("quota test"); }; });
    const failed = await blocked.newPage();
    await failed.goto(url); await failed.locator(".case-row").first().click();
    await failed.getByRole("tab", { name: "Review", exact: true }).click();
    await failed.locator("#review-notes").fill("Memory only QA");
    await failed.getByRole("button", { name: "Save local review", exact: true }).click();
    assert.match(await failed.locator("#storage-status").textContent(), /Not saved.*quota test/);
    let warned = false;
    failed.on("dialog", async (dialog) => { warned = dialog.type() === "beforeunload"; await dialog.accept(); });
    await failed.goto("about:blank"); assert.equal(warned, true);
    await blocked.close();
  } finally { await browser.close(); await new Promise((resolve) => server.close(resolve)); }
});
