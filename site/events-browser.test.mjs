import assert from "node:assert/strict";
import { test } from "node:test";
import { createServer } from "node:http";
import { readFile, mkdir } from "node:fs/promises";
import { pathToFileURL, fileURLToPath } from "node:url";
import { toRows, filterEventRows } from "./events.mjs";

test("Events search, investigation links, CSV and offline desktop/mobile layouts", {
  skip: !process.env.INVESTIGATIONS_PLAYWRIGHT,
}, async () => {
  const { chromium } = await import(pathToFileURL(process.env.INVESTIGATIONS_PLAYWRIGHT));
  const payload = JSON.parse(await readFile(new URL("../holo-view-maker/public/data/events.json", import.meta.url), "utf8"));
  const first = payload.events.find((e) => e.state && e.riskLevel);
  assert.ok(first, "A saved real India export is required for browser QA");
  const server = createServer(async (request, response) => {
    try {
      const path = new URL(request.url, "http://localhost").pathname;
      const data = path === "/globe/data/events.json";
      const name = data ? "events.json" : path.slice(1);
      if (!/^[a-zA-Z0-9_.-]+$/.test(name)) throw new Error("Unknown resource");
      const base = data ? new URL("../holo-view-maker/public/data/", import.meta.url) : new URL("./", import.meta.url);
      const body = await readFile(new URL(name, base));
      response.setHeader("Content-Type", /\.m?js$/.test(name) ? "text/javascript" : name.endsWith(".css") ? "text/css" : data ? "application/json" : "text/html");
      response.end(body);
    } catch {
      response.statusCode = 404;
      response.end("Not found");
    }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  const screenshotDir = new URL("../output/sih-demo/", import.meta.url);
  await mkdir(screenshotDir, { recursive: true });
  try {
    for (const [name, width, height] of [["desktop", 1440, 1000], ["mobile", 390, 844]]) {
      const page = await browser.newPage({ viewport: { width, height }, acceptDownloads: true });
      const errors = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.route("**/*", (route) => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
      await page.goto(`${origin}/events.html`);
      await page.locator(".rowcount").waitFor();
      const query = `${first.state} ${first.riskLevel}`;
      await page.locator("#search").fill(query);
      const expected = filterEventRows(toRows(payload.events), query).length;
      assert.ok((await page.locator(".rowcount").innerText()).startsWith(`${expected.toLocaleString("en-US")} `));
      await page.locator("#search").fill(first.id);
      assert.equal(await page.locator("tbody tr").count(), 1);
      assert.equal(await page.locator("tbody a").innerText(), first.id);
      assert.equal(await page.locator(".more").isVisible(), false);
      assert.equal((await page.locator("#meta").innerText()).includes("undefined"), false);
      assert.ok((await page.locator("#meta").innerText()).includes("Last observed"));
      await page.screenshot({ path: fileURLToPath(new URL(`events-${name}.png`, screenshotDir)), fullPage: true });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      const downloaded = page.waitForEvent("download");
      await page.locator("#export-btn").click();
      const download = await downloaded;
      const csv = await readFile(await download.path(), "utf8");
      assert.ok(csv.includes(first.id));
      await page.locator("#search").fill("no-such-event-zzzz");
      assert.equal(await page.locator("tbody").innerText(), "No matching events.");
      await page.locator("#search").fill(first.id);
      await page.locator("tbody a").click();
      await page.locator("#dossier-title").waitFor();
      await page.waitForFunction((id) => document.querySelector("#dossier-title")?.textContent.includes(id), first.id);
      await page.screenshot({ path: fileURLToPath(new URL(`investigation-${name}.png`, screenshotDir)), fullPage: true });
      assert.deepEqual(errors, []);
      await page.close();
    }
    if (process.env.THERMAL_APP_URL) {
      const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
      await page.goto(process.env.THERMAL_APP_URL);
      const search = page.getByRole("textbox", { name: "Search", exact: true });
      await search.waitFor({ timeout: 45000 });
      await search.fill(first.id);
      await search.press("Enter");
      await page.screenshot({ path: fileURLToPath(new URL("dashboard-search-debug.png", screenshotDir)), fullPage: true });
      await page.getByRole("button", { name: /Open event/ }).waitFor();
      await page.screenshot({ path: fileURLToPath(new URL("dashboard-search.png", screenshotDir)), fullPage: true });
      await page.getByRole("button", { name: /Open event/ }).click();
      await page.getByRole("heading", { name: `Thermal event ${first.id}` }).waitFor();
      const downloaded = page.waitForEvent("download");
      await page.getByRole("button", { name: "Report (text)", exact: true }).click();
      const download = await downloaded;
      assert.ok((await readFile(await download.path(), "utf8")).includes(first.id));
      await page.screenshot({ path: fileURLToPath(new URL("dashboard-investigation.png", screenshotDir)), fullPage: true });
      await page.getByRole("button", { name: /Open 3D globe/ }).click();
      await page.waitForFunction((id) => [...document.querySelectorAll("iframe")].some((frame) => frame.src.includes(`event=${id}`)), first.id);
      assert.equal(await page.locator('[data-testid="stException"]').count(), 0);
      await page.close();
    }
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
});
