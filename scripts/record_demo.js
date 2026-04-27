/**
 * Scripted demo recording — drives the live app at localhost:3000 via
 * Playwright Chromium with video recording enabled. Output: docs/demo.webm
 * (then converted to docs/demo.mp4 by record_demo.sh).
 */
const { chromium } = require("playwright");
const path = require("path");

const BASE = process.env.TRIO_DEMO_URL || "http://127.0.0.1:3000";
const VIEWPORT = { width: 1280, height: 720 };
const RAW_OUT = path.resolve(__dirname, "..", "docs", "demo_raw");

// Pacing helpers — the recording is real-time, so these set the visual rhythm.
const HOLD_SHORT = 800;
const HOLD = 1500;
const HOLD_LONG = 2500;
const READ = 4000;     // long enough for a viewer to read a label

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function highlight(page, selector, label) {
  // Brief soft glow on a target — pure visual breadcrumb for the viewer.
  try {
    await page.locator(selector).first().evaluate((el) => {
      el.style.transition = "box-shadow 200ms ease, transform 200ms ease";
      el.style.boxShadow = "0 0 0 4px rgba(29, 78, 216, 0.55)";
      el.style.transform = "scale(1.015)";
    });
    await sleep(900);
    await page.locator(selector).first().evaluate((el) => {
      el.style.boxShadow = "";
      el.style.transform = "";
    });
  } catch {
    // ignore — selector may not exist yet
  }
}

async function main() {
  console.log("Launching Chromium...");
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    recordVideo: { dir: RAW_OUT, size: VIEWPORT },
  });
  const page = await context.newPage();

  console.log(`Loading ${BASE}...`);
  await page.goto(BASE, { waitUntil: "networkidle" });
  await sleep(HOLD_LONG);

  // ── Scene 1 — header / branding ────────────────────────────────────
  console.log("Scene 1 — header");
  await highlight(page, "header h1");
  await sleep(HOLD);
  await highlight(page, "header button:has-text('BYOK')");
  await sleep(HOLD_LONG);

  // ── Scene 2 — sample data → BOS watchlist ─────────────────────────
  console.log("Scene 2 — sample data BOS");
  await highlight(page, "button:has-text('Try sample')");
  await sleep(HOLD_SHORT);
  await page.click("button:has-text('Try sample')");
  await page.waitForSelector("section:has-text('Ranked watchlist') table", {
    timeout: 15000,
  });
  await sleep(HOLD);
  await page.locator("section:has-text('Ranked watchlist')").scrollIntoViewIfNeeded();
  await sleep(HOLD_LONG);

  // ── Scene 3 — switch to BOS-Flow → 7 factors ───────────────────────
  console.log("Scene 3 — switch model to BOS-Flow");
  await page.locator("section:has-text('Choose model')").scrollIntoViewIfNeeded();
  await sleep(HOLD_SHORT);
  // The first model select is in the upload card (1. Choose model & universe)
  const modelSelect = page.locator("select").first();
  await highlight(page, "label:has-text('Model')");
  await sleep(HOLD_SHORT);
  await modelSelect.selectOption("bos_flow");
  await sleep(HOLD_SHORT);
  await page.click("button:has-text('Try sample')");
  await page.waitForSelector("section:has-text('Ranked watchlist') table");
  await sleep(HOLD);
  await page.locator("section:has-text('Ranked watchlist')").scrollIntoViewIfNeeded();
  await sleep(HOLD_LONG);

  // ── Scene 4 — open stock detail → radar ────────────────────────────
  console.log("Scene 4 — stock detail + radar");
  // Click first row in the watchlist
  await page.locator("section:has-text('Ranked watchlist') table tbody tr").first().click();
  await page.waitForSelector("h2:has-text('MAYBANK MK'), h2:has-text('PCHEM MK'), h2:has-text('PBBANK MK')", {
    timeout: 5000,
  }).catch(() => {});
  await sleep(READ);
  // Close modal
  await page.locator("button[aria-label='Close']").first().click();
  await sleep(HOLD_SHORT);

  // ── Scene 5 — drag a factor weight slider ─────────────────────────
  console.log("Scene 5 — weight sliders");
  await page.locator("section:has-text('Tune factor weights')").scrollIntoViewIfNeeded();
  await sleep(HOLD);
  await highlight(page, "section:has-text('Tune factor weights')");
  await sleep(HOLD);
  // Drag the F6 slider (Insider Flow) significantly to the right
  const f6Slider = page.locator("input[type='range']").nth(5);  // F1..F5..F6 = idx 5
  const box = await f6Slider.boundingBox();
  if (box) {
    await page.mouse.move(box.x + box.width * 0.5, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * 0.85, box.y + box.height / 2, { steps: 12 });
    await page.mouse.up();
  }
  await sleep(HOLD_LONG);

  // ── Scene 6 — universe preset + scoring ────────────────────────────
  console.log("Scene 6 — curated universe pill");
  await page.locator("section:has-text('Or fetch a live universe')").scrollIntoViewIfNeeded();
  await sleep(HOLD_SHORT);
  // Click the curated demo pill (28 US large caps)
  const pill = page.locator("button[title*='28']").first();
  if (await pill.count()) {
    await highlight(page, "button[title*='28']");
    await sleep(HOLD_SHORT);
    await pill.click();
    await sleep(HOLD);
  }

  // ── Scene 7 — backtest card ────────────────────────────────────────
  console.log("Scene 7 — backtest card");
  // Scope tightly to the backtest section (h2 "4. Backtest")
  const backtestCard = page.locator("section:has(h2:has-text('4. Backtest'))").first();
  await backtestCard.scrollIntoViewIfNeeded();
  await sleep(HOLD_LONG);
  // Soft-highlight via scope
  try {
    await backtestCard.evaluate((el) => {
      el.style.transition = "box-shadow 200ms ease";
      el.style.boxShadow = "0 0 0 4px rgba(29, 78, 216, 0.55)";
    });
    await sleep(HOLD);
    await backtestCard.evaluate((el) => { el.style.boxShadow = ""; });
  } catch {}

  // ── Scene 8 — outro: scroll back to top, hold on hero ─────────────
  console.log("Scene 8 — outro");
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await sleep(HOLD_LONG);

  // Close (writes the video file)
  await context.close();
  await browser.close();
  console.log("Recording done. Raw video in:", RAW_OUT);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
