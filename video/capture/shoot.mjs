/**
 * Captures the real pages the video shows into public/shots/<name>.png with
 * a sidecar <name>.json {url, captured_at, viewport, width, height,
 * pii_reviewed, redactions}. Playwright, either its own Chromium or the
 * user's Chrome over CDP (for logged-in pages):
 *
 *   open -na "Google Chrome" --args --remote-debugging-port=9222 --user-data-dir="$HOME/chrome-shoot"
 *   node capture/shoot.mjs --cdp http://127.0.0.1:9222 [--only name] [--dismiss "selector"]
 *
 * Redaction selectors from shots.manifest.json (or --redact "sel1,sel2") are
 * blurred with a CSS filter before the shot; the sidecar starts with
 * pii_reviewed:false and is flipped by hand after looking at the PNG.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";
import { pngSize } from "./collect-shots.mjs";

const VIDEO = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const OUT = join(VIDEO, "public", "shots");
const manifest = JSON.parse(readFileSync(join(VIDEO, "capture", "shots.manifest.json"), "utf8"));

const argOf = (name) => {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : undefined;
};
const cdp = argOf("--cdp");
const only = argOf("--only");
const extraRedact = (argOf("--redact") ?? "").split(",").map((s) => s.trim()).filter(Boolean);
const dismiss = argOf("--dismiss");

mkdirSync(OUT, { recursive: true });
const browser = cdp ? await chromium.connectOverCDP(cdp) : await chromium.launch();
const context = cdp ? browser.contexts()[0] ?? (await browser.newContext()) : await browser.newContext({ viewport: manifest.viewport, deviceScaleFactor: 1 });
const today = new Date().toISOString().slice(0, 10);

for (const shot of manifest.shots) {
  if (only && shot.name !== only) continue;
  const page = await context.newPage();
  await page.setViewportSize(manifest.viewport);
  try {
    await page.goto(shot.url, { waitUntil: "networkidle", timeout: 60000 }).catch(() => page.waitForTimeout(3000));
    await page.waitForTimeout(shot.waitMs ?? 1500);
    if (dismiss) await page.locator(dismiss).first().click({ timeout: 2000 }).catch(() => {});
    const hide = [...(manifest.hide ?? []), ...(shot.hide ?? [])];
    if (hide.length) await page.addStyleTag({ content: `${hide.join(",")}{display:none!important}` });
    if (shot.click) await page.locator(shot.click).first().click({ timeout: 4000 }).catch((e) => console.error(`    (click ${shot.click} failed: ${e.message.split("\n")[0]})`));
    if (shot.dismiss) await page.locator(shot.dismiss).first().click({ timeout: 2000 }).catch(() => {});
    if (typeof shot.scrollTo === "number") {
      await page.evaluate((y) => window.scrollTo(0, y), shot.scrollTo);
    } else if (typeof shot.scrollTo === "string") {
      const loc = page.locator(shot.scrollTo).first();
      await loc.scrollIntoViewIfNeeded({ timeout: 5000 }).catch(() => {});
      await page.evaluate((dy) => window.scrollBy(0, dy), shot.scrollBy ?? -120);
    }
    const redactions = [...(shot.redact ?? []), ...extraRedact.map((selector) => ({ selector, reason: "cli" }))];
    if (redactions.length) {
      await page.addStyleTag({ content: redactions.map((r) => `${r.selector}{filter:blur(14px)!important}`).join("\n") });
    }
    await page.waitForTimeout(400);
    const file = join(OUT, `${shot.name}.png`);
    const maxH = shot.maxHeight ?? manifest.maxHeight;
    if (shot.fullPage) {
      const h = await page.evaluate(() => document.documentElement.scrollHeight);
      await page.screenshot({ path: file, clip: { x: 0, y: 0, width: manifest.viewport.width, height: Math.min(h, maxH) }, fullPage: true });
    } else {
      await page.screenshot({ path: file, fullPage: false });
    }
    const { width, height } = pngSize(file);
    const prev = existsSync(join(OUT, `${shot.name}.json`)) ? JSON.parse(readFileSync(join(OUT, `${shot.name}.json`), "utf8")) : {};
    writeFileSync(
      join(OUT, `${shot.name}.json`),
      `${JSON.stringify({ url: shot.url, captured_at: today, tool: `capture/shoot.mjs (playwright${cdp ? " over CDP" : ""})`, viewport: { ...manifest.viewport, dpr: 1 }, width, height, full_page: Boolean(shot.fullPage), pii_reviewed: prev.pii_reviewed === true && prev.captured_at === today ? true : false, redactions }, null, 2)}\n`,
    );
    console.log(`  ✓ ${shot.name.padEnd(22)} ${width}×${height}  ${shot.url}`);
  } catch (e) {
    console.error(`  ✗ ${shot.name}: ${e.message}`);
  } finally {
    await page.close();
  }
}
if (!cdp) await browser.close();
else await browser.close().catch(() => {});
