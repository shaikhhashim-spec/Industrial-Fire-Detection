import assert from "node:assert/strict";
import { test } from "node:test";
import { createServer } from "node:http";
import { readFile, mkdir } from "node:fs/promises";
import { pathToFileURL, fileURLToPath } from "node:url";

test("public global workspace navigation, settings and globe on desktop/mobile", {
  skip: !process.env.INVESTIGATIONS_PLAYWRIGHT,
  timeout: 180000,
}, async () => {
  const { chromium } = await import(pathToFileURL(process.env.INVESTIGATIONS_PLAYWRIGHT));
  const root = new URL("../output/public-preview/", import.meta.url);
  const screenshots = new URL("../output/public-workspace-qa/", import.meta.url);
  await mkdir(screenshots, { recursive: true });
  const server = createServer(async (request, response) => {
    try {
      const path = new URL(request.url, "http://localhost").pathname;
      if (!/^\/[a-zA-Z0-9_./-]*$/.test(path) || path.includes("..")) throw new Error("Invalid resource");
      const name = path.endsWith("/") ? `${path.slice(1)}index.html` : path.slice(1);
      const body = await readFile(new URL(name, root));
      response.setHeader("Content-Type", /\.m?js$/.test(name) ? "text/javascript" : name.endsWith(".css") ? "text/css" : name.endsWith(".json") ? "application/json" : name.endsWith(".png") ? "image/png" : name.endsWith(".webp") ? "image/webp" : "text/html");
      response.end(body);
    } catch { response.statusCode = 404; response.end("Not found"); }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    for (const [name, width, height] of [["desktop", 1440, 1000], ["mobile", 390, 844]]) {
      const page = await browser.newPage({ viewport: { width, height }, acceptDownloads: true });
      const errors = []; page.on("pageerror", (error) => errors.push(error.message));
      await page.goto(`${origin}/alerts.html?region=global`);
      await page.locator(".scope-note").waitFor();
      assert.equal(await page.locator("#region").inputValue(), "global");
      assert.match(await page.locator(".scope-note").innerText(), /Global snapshot/);
      assert.equal((await page.locator(".side-note").innerText()).includes("localhost"), false);
      const alert = page.locator(".alertcard a.id").first();
      const id = await alert.innerText();
      await page.locator("#search").fill(id);
      await page.screenshot({ path: fileURLToPath(new URL(`alerts-${name}.png`, screenshots)), fullPage: true });
      await page.locator(".alertcard a.id").first().click();
      await page.waitForFunction((id) => document.querySelector("#dossier-title")?.textContent.includes(id), id);
      assert.equal(new URL(page.url()).searchParams.get("region"), "global");
      await page.locator("#nav a").filter({ hasText: /^Events$/ }).click();
      await page.locator(".rowcount").waitFor();
      assert.equal(await page.locator("#region").inputValue(), "global");
      await page.locator("#search").fill(id);
      assert.equal(await page.locator("tbody a").first().innerText(), id);
      await page.locator("#filter-risk").selectOption("HIGH");
      await page.locator("#filter-risk").selectOption("");
      await page.locator("#nav a").filter({ hasText: /^Analytics$/ }).click();
      await page.locator(".scope-note").waitFor();
      assert.equal(await page.locator("#region").inputValue(), "global");
      await page.locator("#nav a").filter({ hasText: /^Overview$/ }).click();
      await page.locator(".statrow").waitFor();
      assert.equal(new URL(page.url()).searchParams.get("view"), "overview");
      assert.equal(await page.locator("#region").inputValue(), "global");
      await page.locator("#nav a").filter({ hasText: /^Settings$/ }).click();
      await page.locator("#page-size").waitFor();
      await page.locator("#page-size").selectOption("50");
      await page.getByRole("button", { name: "Save preferences" }).click();
      assert.match(await page.getByText("Personal preferences saved in this browser.").innerText(), /saved/);
      const downloading = page.waitForEvent("download");
      await page.getByRole("button", { name: "Download snapshot" }).click();
      const snapshot = JSON.parse(await readFile(await (await downloading).path(), "utf8"));
      assert.equal(snapshot.meta.scope, "global");
      await page.screenshot({ path: fileURLToPath(new URL(`settings-${name}.png`, screenshots)), fullPage: true });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await page.locator("#nav a").filter({ hasText: /^Events$/ }).click();
      await page.locator(".rowcount").waitFor();
      assert.equal(await page.locator("tbody tr").count(), 50);
      await page.locator("#nav a").filter({ hasText: /^3D Globe Model$/ }).click();
      await page.locator("canvas").first().waitFor({ timeout: 45000 });
      await page.getByRole("link", { name: "Events", exact: true }).waitFor();
      const canvas = page.locator("canvas").first();
      assert.ok(await canvas.evaluate((element) => element.width > 100 && element.height > 100));
      await page.screenshot({ path: fileURLToPath(new URL(`globe-${name}.png`, screenshots)), fullPage: true });
      const before = await canvas.screenshot();
      const bounds = await canvas.boundingBox();
      await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
      await page.mouse.down();
      await page.mouse.move(bounds.x + bounds.width / 2 + 70, bounds.y + bounds.height / 2, { steps: 15 });
      await page.mouse.up();
      assert.notDeepEqual(await canvas.screenshot(), before, "Dragging must change the rendered globe");
      await page.getByRole("link", { name: "Events", exact: true }).click();
      await page.locator(".rowcount").waitFor();
      assert.equal(await page.locator("#region").inputValue(), "global");
      assert.deepEqual(errors, []);
      await page.close();
    }
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
});
