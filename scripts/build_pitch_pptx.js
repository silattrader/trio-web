/**
 * Generate docs/PITCH.pptx from the content baked into PITCH.md.
 * Run: node scripts/build_pitch_pptx.js
 */
const pptxgen = require("pptxgenjs");

// --- Palette (financial-services aesthetic) -------------------------------
const NAVY    = "1E293B";  // slate-800 — backgrounds, primary text
const SLATE   = "475569";  // slate-600 — body text
const MUTED   = "94A3B8";  // slate-400 — captions
const PAPER   = "F8FAFC";  // slate-50  — light backgrounds
const RULE    = "E2E8F0";  // slate-200 — dividers
const TRUST   = "1D4ED8";  // blue-700  — accent (links, primary)
const ACCENT  = "0EA5E9";  // sky-500   — secondary accent
const SUCCESS = "059669";  // emerald-600 — positive numbers
const DANGER  = "DC2626";  // red-600   — negative numbers
const AMBER   = "D97706";  // amber-600 — caution

// --- Setup ---------------------------------------------------------------
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.title  = "TRIO Web — Transparent factor scoring";
pres.author = "silattrader";
pres.company = "TRIO Web";

const W = 10;       // slide width (in)
const H = 5.625;    // slide height
const MX = 0.55;    // horizontal margin

// --- Reusable: footer + slide-number bar ---------------------------------
function footer(slide, n, total) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: H - 0.32, w: W, h: 0.32, fill: { color: NAVY }, line: { type: "none" },
  });
  slide.addText("github.com/silattrader/trio-web  ·  Decision-support only — not investment advice", {
    x: MX, y: H - 0.32, w: W - 2 * MX, h: 0.32,
    fontSize: 9, color: MUTED, fontFace: "Calibri", valign: "middle", margin: 0,
  });
  slide.addText(`${n} / ${total}`, {
    x: W - 1.0, y: H - 0.32, w: 0.5, h: 0.32,
    fontSize: 9, color: MUTED, fontFace: "Calibri", align: "right", valign: "middle", margin: 0,
  });
}

function slideTitle(slide, eyebrow, title) {
  if (eyebrow) {
    slide.addText(eyebrow.toUpperCase(), {
      x: MX, y: 0.35, w: W - 2 * MX, h: 0.3,
      fontSize: 11, color: TRUST, bold: true, charSpacing: 6, fontFace: "Calibri",
      margin: 0,
    });
  }
  slide.addText(title, {
    x: MX, y: 0.65, w: W - 2 * MX, h: 0.85,
    fontSize: 28, bold: true, color: NAVY, fontFace: "Calibri", margin: 0,
  });
}

const TOTAL = 11;

// === Slide 1: TITLE ======================================================
{
  const s = pres.addSlide();
  s.background = { color: NAVY };

  // Accent strip down the left
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.18, h: H, fill: { color: TRUST }, line: { type: "none" } });

  s.addText("TRIO  WEB", {
    x: 0.7, y: 0.7, w: 8, h: 0.5,
    fontSize: 14, bold: true, color: ACCENT, charSpacing: 8, fontFace: "Calibri",
  });

  s.addText("Transparent factor scoring\nfor everyone", {
    x: 0.7, y: 1.5, w: 9, h: 2.0,
    fontSize: 50, bold: true, color: "FFFFFF", fontFace: "Calibri",
    paraSpaceAfter: 6,
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: 3.7, w: 1.8, h: 0.04, fill: { color: ACCENT }, line: { type: "none" },
  });

  s.addText([
    { text: "7-factor PIT-honest scoring  ·  RBA + ML  ·  walk-forward verified", options: { breakLine: true, fontSize: 16, color: "CBD5E1" } },
    { text: "Open source  ·  github.com/silattrader/trio-web", options: { fontSize: 14, color: MUTED } },
  ], { x: 0.7, y: 3.9, w: 9, h: 1.0, fontFace: "Calibri" });

  s.addText("Hackathon Pitch  ·  2026", {
    x: 0.7, y: H - 0.7, w: 6, h: 0.3,
    fontSize: 11, color: MUTED, fontFace: "Calibri",
  });

  // Speaker notes
  s.addNotes(
    "Open with energy. Two camps in equity analysis: retail traders drowning in hot takes, " +
    "institutional fund managers paying $24k per Bloomberg seat. The audience is whoever cares about " +
    "honest, transparent, point-in-time-correct equity scoring — and we built it free, open-source."
  );
}

// === Slide 2: PROBLEM ====================================================
{
  const s = pres.addSlide();
  s.background = { color: PAPER };
  slideTitle(s, "Slide 1 of 11  ·  Problem", "The retail-vs-institutional divide");

  // Two-column comparison
  const yCol = 1.8;
  const colH = 2.7;
  const colW = 4.3;

  // RETAIL column
  s.addShape(pres.shapes.RECTANGLE, { x: MX, y: yCol, w: colW, h: colH, fill: { color: "FFFFFF" }, line: { color: RULE, width: 0.5 } });
  s.addShape(pres.shapes.RECTANGLE, { x: MX, y: yCol, w: 0.08, h: colH, fill: { color: ACCENT }, line: { type: "none" } });
  s.addText("RETAIL TRADERS", { x: MX + 0.25, y: yCol + 0.2, w: colW - 0.4, h: 0.3, fontSize: 12, bold: true, color: ACCENT, charSpacing: 4, fontFace: "Calibri", margin: 0 });
  s.addText([
    { text: "YouTube hot-takes  ·  Reddit hype  ·  WhatsApp signal services", options: { breakLine: true, fontSize: 14, color: NAVY } },
    { text: "", options: { breakLine: true, fontSize: 6 } },
    { text: "Optimize for engagement, not honesty.", options: { italic: true, color: SLATE, fontSize: 13, breakLine: true } },
    { text: "", options: { breakLine: true, fontSize: 6 } },
    { text: "Lookahead bias is rampant.", options: { bold: true, color: DANGER, fontSize: 13 } },
  ], { x: MX + 0.25, y: yCol + 0.6, w: colW - 0.4, h: colH - 0.7, fontFace: "Calibri", valign: "top" });

  // INSTITUTIONAL column
  const x2 = MX + colW + 0.4;
  s.addShape(pres.shapes.RECTANGLE, { x: x2, y: yCol, w: colW, h: colH, fill: { color: "FFFFFF" }, line: { color: RULE, width: 0.5 } });
  s.addShape(pres.shapes.RECTANGLE, { x: x2, y: yCol, w: 0.08, h: colH, fill: { color: TRUST }, line: { type: "none" } });
  s.addText("INSTITUTIONAL FUND MANAGERS", { x: x2 + 0.25, y: yCol + 0.2, w: colW - 0.4, h: 0.3, fontSize: 12, bold: true, color: TRUST, charSpacing: 4, fontFace: "Calibri", margin: 0 });
  s.addText([
    { text: "Bloomberg ($24k/seat/yr)  ·  Refinitiv  ·  FactSet", options: { breakLine: true, fontSize: 14, color: NAVY } },
    { text: "", options: { breakLine: true, fontSize: 6 } },
    { text: "Capability gated by ability to pay,", options: { italic: true, color: SLATE, fontSize: 13, breakLine: true } },
    { text: "not by the question being asked.", options: { italic: true, color: SLATE, fontSize: 13 } },
  ], { x: x2 + 0.25, y: yCol + 0.6, w: colW - 0.4, h: colH - 0.7, fontFace: "Calibri", valign: "top" });

  // Bottom takeaway
  s.addText([
    { text: "Nobody ships ", options: {} },
    { text: "transparent, factor-based, point-in-time-honest", options: { bold: true, color: NAVY } },
    { text: " equity analysis as ", options: {} },
    { text: "free, open infrastructure.", options: { bold: true, color: TRUST } },
  ], {
    x: MX, y: yCol + colH + 0.3, w: W - 2 * MX, h: 0.6,
    fontSize: 16, color: SLATE, fontFace: "Calibri", align: "center", margin: 0,
  });

  footer(s, 1, TOTAL);
  s.addNotes(
    "Open with the pain. KWAP runs RM 185 billion through Bloomberg. A Malaysian retail trader has " +
    "WhatsApp groups. The tooling gap is real and offensive — and it's the gap we set out to fill."
  );
}

// === Slide 3: SOLUTION ==================================================
{
  const s = pres.addSlide();
  s.background = { color: PAPER };
  slideTitle(s, "Slide 2 of 11  ·  Solution", "TRIO Web — one engine, both audiences");

  // Big tagline
  s.addText([
    { text: "Transparent ", options: {} },
    { text: "7-factor", options: { bold: true, color: TRUST } },
    { text: " equity scoring with a ", options: {} },
    { text: "gate-passed ML model", options: { bold: true, color: TRUST } },
    { text: "." , options: {} },
  ], {
    x: MX, y: 1.7, w: W - 2 * MX, h: 0.5,
    fontSize: 18, color: NAVY, fontFace: "Calibri", margin: 0,
  });

  // Four pillars in a 2x2 grid
  const pillars = [
    { ic: "5+1", title: "5 RBA engines + 1 MLA", body: "BOS, BOS-Flow, MOS-Graham, 4-Factor, MLA. Single stable JSON contract — UI never branches." },
    { ic: "PIT", title: "Point-in-time data", body: "SEC EDGAR · Form 4 · Wikipedia attention · FMP analyst consensus. filed ≤ as_of. Zero lookahead." },
    { ic: "BYOK", title: "Bring-your-own-keys", body: "No accounts, no Stripe, no SaaS infrastructure. Users plug free API keys; we call providers as them." },
    { ic: "OSS", title: "Open source · MIT", body: "Public repo · 140 tests passing · CI green. Anyone can fork, audit, or self-host on day one." },
  ];

  const gx = [MX, MX + 4.55];
  const gy = [2.4, 3.85];
  const cardW = 4.35, cardH = 1.3;

  pillars.forEach((p, i) => {
    const cx = gx[i % 2], cy = gy[Math.floor(i / 2)];
    s.addShape(pres.shapes.RECTANGLE, { x: cx, y: cy, w: cardW, h: cardH, fill: { color: "FFFFFF" }, line: { color: RULE, width: 0.5 } });
    // Icon-tag
    s.addShape(pres.shapes.RECTANGLE, { x: cx, y: cy, w: 0.85, h: cardH, fill: { color: NAVY }, line: { type: "none" } });
    s.addText(p.ic, { x: cx, y: cy, w: 0.85, h: cardH, fontSize: 14, bold: true, color: ACCENT, fontFace: "Calibri", align: "center", valign: "middle", margin: 0 });
    s.addText(p.title, { x: cx + 0.95, y: cy + 0.15, w: cardW - 1.0, h: 0.4, fontSize: 13, bold: true, color: NAVY, fontFace: "Calibri", margin: 0 });
    s.addText(p.body, { x: cx + 0.95, y: cy + 0.55, w: cardW - 1.0, h: cardH - 0.6, fontSize: 11, color: SLATE, fontFace: "Calibri", margin: 0, valign: "top" });
  });

  footer(s, 2, TOTAL);
  s.addNotes(
    "Same engine serves a retail trader picking 5 stocks for their EPF top-up AND a family office vetting " +
    "a new long-short basket. The contract is identical; only the audience-facing copy differs."
  );
}

// === Slide 4: INNOVATION =================================================
{
  const s = pres.addSlide();
  s.background = { color: PAPER };
  slideTitle(s, "Slide 3 of 11  ·  Innovation", "What's genuinely new");

  s.addText("We didn't reinvent factor scoring. We integrated four things that don't usually live together.", {
    x: MX, y: 1.55, w: W - 2 * MX, h: 0.4,
    fontSize: 13, italic: true, color: SLATE, fontFace: "Calibri", margin: 0,
  });

  const tableData = [
    [
      { text: "ELEMENT", options: { bold: true, color: "FFFFFF", fill: { color: NAVY }, align: "left", fontSize: 11 } },
      { text: "WHY IT MATTERS", options: { bold: true, color: "FFFFFF", fill: { color: NAVY }, align: "left", fontSize: 11 } },
    ],
    [
      { text: "Composable PIT data pipeline", options: { bold: true, color: NAVY, fontSize: 12 } },
      { text: "Most free tools cheat with today's fundamentals. We pull filed ≤ as_of from SEC EDGAR. No lookahead.", options: { color: SLATE, fontSize: 11 } },
    ],
    [
      { text: "Dual RBA + MLA with hard promotion gate", options: { bold: true, color: NAVY, fontSize: 12 } },
      { text: "Rule-based ships first. ML can only replace it after backtesting better. Institutional governance, in open source.", options: { color: SLATE, fontSize: 11 } },
    ],
    [
      { text: "Walk-forward verified, not single-window", options: { bold: true, color: NAVY, fontSize: 12 } },
      { text: "We published the 2 windows where the model lost. Rigor judges who've trained models will recognize.", options: { color: SLATE, fontSize: 11 } },
    ],
    [
      { text: "BYOK = free for everyone, scalable forever", options: { bold: true, color: NAVY, fontSize: 12 } },
      { text: "No paywall. Retail uses free tiers. Institutions plug in their existing $24k Bloomberg key.", options: { color: SLATE, fontSize: 11 } },
    ],
  ];

  s.addTable(tableData, {
    x: MX, y: 2.05, w: W - 2 * MX, colW: [3.4, 5.5],
    border: { type: "solid", pt: 0.5, color: RULE },
    fontFace: "Calibri",
    rowH: [0.4, 0.65, 0.65, 0.65, 0.65],
    fill: { color: "FFFFFF" },
  });

  footer(s, 3, TOTAL);
  s.addNotes(
    "Each row in this table is a deliberate architectural choice with a tradeoff. PIT cost us months of " +
    "plumbing complexity. The promotion gate cost us 'MLA always wins' marketing. BYOK cost us recurring revenue. " +
    "We made the honest choice every time."
  );
}

// === Slide 5: LIVE DEMO ==================================================
{
  const s = pres.addSlide();
  s.background = { color: PAPER };
  slideTitle(s, "Slide 4 of 11  ·  Demo", "Live demo — what you can do right now");

  s.addText([
    { text: "Open ", options: {} },
    { text: "github.com/silattrader/trio-web", options: { color: TRUST, bold: true } },
    { text: " · Vercel deploy ready in ", options: {} },
    { text: "docs/DEPLOY.md", options: { fontFace: "Consolas", color: NAVY } },
    { text: " (10 min)", options: {} },
  ], {
    x: MX, y: 1.55, w: W - 2 * MX, h: 0.35, fontSize: 12, color: SLATE, fontFace: "Calibri", margin: 0,
  });

  const tableData = [
    [
      { text: "ACTION", options: { bold: true, color: "FFFFFF", fill: { color: NAVY }, fontSize: 11 } },
      { text: "RESULT", options: { bold: true, color: "FFFFFF", fill: { color: NAVY }, fontSize: 11 } },
    ],
    [{ text: "Click  Try sample", options: { bold: true, color: NAVY, fontSize: 11 } }, { text: "8 KLCI tickers ranked · factor radar · BUY-BUY → SELL-SELL chips", options: { color: SLATE, fontSize: 11 } }],
    [{ text: "Switch model: BOS → BOS-Flow → MLA-v0", options: { bold: true, color: NAVY, fontSize: 11 } }, { text: "Same universe, three opinions, side by side", options: { color: SLATE, fontSize: 11 } }],
    [{ text: "Drag a factor weight slider", options: { bold: true, color: NAVY, fontSize: 11 } }, { text: "Watchlist re-ranks live in 350 ms (debounced)", options: { color: SLATE, fontSize: 11 } }],
    [{ text: "Pick S&P 500 top 100 preset → Fetch", options: { bold: true, color: NAVY, fontSize: 11 } }, { text: "Real yfinance fetch + scoring in ~5 seconds", options: { color: SLATE, fontSize: 11 } }],
    [{ text: "Paste FMP key in BYOK panel", options: { bold: true, color: NAVY, fontSize: 11 } }, { text: "Live PIT analyst data flows; coverage badges flip green", options: { color: SLATE, fontSize: 11 } }],
    [{ text: "Run SMA backtest on AAPL/MSFT/NVDA", options: { bold: true, color: NAVY, fontSize: 11 } }, { text: "Equity curve vs benchmark · CAGR · Sharpe · MaxDD", options: { color: SLATE, fontSize: 11 } }],
    [{ text: "Toggle Walk-forward", options: { bold: true, color: NAVY, fontSize: 11 } }, { text: "4 OOS windows, per-window stats, aggregate dispersion", options: { color: SLATE, fontSize: 11 } }],
  ];

  s.addTable(tableData, {
    x: MX, y: 2.0, w: W - 2 * MX, colW: [3.7, 5.2],
    border: { type: "solid", pt: 0.5, color: RULE },
    fontFace: "Calibri",
    rowH: [0.35, ...Array(7).fill(0.36)],
    fill: { color: "FFFFFF" },
  });

  footer(s, 4, TOTAL);
  s.addNotes(
    "Don't tell — show. Have the live demo on a second monitor or projector. Run through it in 60 seconds. " +
    "The factor radar is the moment the audience sees what makes this different. Slide 4 is the make-or-break."
  );
}

// === Slide 6: ARCHITECTURE ==============================================
{
  const s = pres.addSlide();
  s.background = { color: PAPER };
  slideTitle(s, "Slide 5 of 11  ·  Architecture", "Built for the long game");

  // Boxes-and-arrows architecture diagram
  // Layout: top = browser, middle = FastAPI, bottom row = 5 modules

  const boxColor = "FFFFFF";
  const boxBorder = NAVY;

  // Browser (top)
  s.addShape(pres.shapes.RECTANGLE, { x: 3.2, y: 1.5, w: 3.6, h: 0.55, fill: { color: NAVY }, line: { type: "none" } });
  s.addText("Browser  ·  Next.js + Tailwind + recharts", {
    x: 3.2, y: 1.5, w: 3.6, h: 0.55, fontSize: 11, bold: true, color: "FFFFFF", fontFace: "Calibri",
    align: "center", valign: "middle", margin: 0,
  });

  // Arrow + label down to API
  s.addShape(pres.shapes.LINE, { x: 5.0, y: 2.05, w: 0, h: 0.5, line: { color: SLATE, width: 1.5, endArrowType: "triangle" } });
  s.addText("/api/* + X-TRIO-* headers  (BYOK)", {
    x: 5.1, y: 2.1, w: 4.5, h: 0.3, fontSize: 9, italic: true, color: SLATE, fontFace: "Calibri", margin: 0,
  });

  // FastAPI middle
  s.addShape(pres.shapes.RECTANGLE, { x: 2.7, y: 2.6, w: 4.6, h: 0.55, fill: { color: TRUST }, line: { type: "none" } });
  s.addText("FastAPI  ·  uvicorn  ·  contextvars middleware", {
    x: 2.7, y: 2.6, w: 4.6, h: 0.55, fontSize: 11, bold: true, color: "FFFFFF", fontFace: "Calibri",
    align: "center", valign: "middle", margin: 0,
  });

  // 5 columns below
  const cols = [
    { t: "RBA", sub: "BOS · Flow\nMOS · 4F" },
    { t: "MLA", sub: "sklearn\nGBM" },
    { t: "Backtester", sub: "SMA · pit\n+ walk-fwd" },
    { t: "PIT data", sub: "EDGAR · FMP\nWiki · Form 4" },
    { t: "Gate", sub: "promotion\nrules" },
  ];

  // Connector lines from FastAPI to each module
  const moduleY = 4.05;
  const moduleH = 1.05;
  const moduleW = 1.65;
  const startX = 0.7;
  const gap = 0.18;

  cols.forEach((c, i) => {
    const cx = startX + i * (moduleW + gap);
    // connector line
    s.addShape(pres.shapes.LINE, {
      x: cx + moduleW / 2, y: 3.15, w: 0, h: moduleY - 3.15,
      line: { color: SLATE, width: 1, endArrowType: "triangle" },
    });
    // module box
    s.addShape(pres.shapes.RECTANGLE, {
      x: cx, y: moduleY, w: moduleW, h: moduleH, fill: { color: boxColor }, line: { color: boxBorder, width: 1 },
    });
    s.addText(c.t, {
      x: cx, y: moduleY + 0.1, w: moduleW, h: 0.35, fontSize: 13, bold: true, color: NAVY, fontFace: "Calibri", align: "center", margin: 0,
    });
    s.addText(c.sub, {
      x: cx, y: moduleY + 0.5, w: moduleW, h: moduleH - 0.55, fontSize: 10, color: SLATE, fontFace: "Calibri", align: "center", margin: 0,
    });
  });

  // Caption strip
  s.addText("monorepo · pure-function backtester · per-request key isolation · cached HTTP layer", {
    x: MX, y: 5.2, w: W - 2 * MX, h: 0.3,
    fontSize: 10, italic: true, color: MUTED, fontFace: "Calibri", align: "center", margin: 0,
  });

  footer(s, 5, TOTAL);
  s.addNotes(
    "This isn't a hackathon hack. The pure-function engine + DI score functions is the kind of architecture " +
    "you'd see in a paid quant platform. We built it that way because we want the demo to scale into real " +
    "product if someone wants to fork it."
  );
}

// === Slide 7: GATE RESULT ===============================================
{
  const s = pres.addSlide();
  s.background = { color: PAPER };
  slideTitle(s, "Slide 6 of 11  ·  Validation", "The numbers that beat sales pitches");

  s.addText("Promotion gate run · 2022–2023 OOS · model trained 2018–2021", {
    x: MX, y: 1.55, w: W - 2 * MX, h: 0.3,
    fontSize: 12, italic: true, color: SLATE, fontFace: "Calibri", margin: 0,
  });

  const gateData = [
    [
      { text: "METRIC", options: { bold: true, color: "FFFFFF", fill: { color: NAVY }, fontSize: 11 } },
      { text: "RBA-BOS-Flow", options: { bold: true, color: "FFFFFF", fill: { color: NAVY }, fontSize: 11, align: "center" } },
      { text: "MLA-7-factor", options: { bold: true, color: "FFFFFF", fill: { color: NAVY }, fontSize: 11, align: "center" } },
      { text: "LIFT", options: { bold: true, color: "FFFFFF", fill: { color: NAVY }, fontSize: 11, align: "center" } },
    ],
    [
      { text: "Total return", options: { color: SLATE, fontSize: 12 } },
      { text: "+9.58%", options: { color: SLATE, fontSize: 12, align: "center" } },
      { text: "+26.36%", options: { color: NAVY, bold: true, fontSize: 12, align: "center" } },
      { text: "+16.78 pp", options: { color: SUCCESS, bold: true, fontSize: 12, align: "center" } },
    ],
    [
      { text: "CAGR", options: { color: SLATE, fontSize: 12 } },
      { text: "+4.73%", options: { color: SLATE, fontSize: 12, align: "center" } },
      { text: "+12.54%", options: { color: NAVY, bold: true, fontSize: 12, align: "center" } },
      { text: "+7.81 pp", options: { color: SUCCESS, bold: true, fontSize: 12, align: "center" } },
    ],
    [
      { text: "Sharpe", options: { color: SLATE, fontSize: 12 } },
      { text: "0.33", options: { color: SLATE, fontSize: 12, align: "center" } },
      { text: "0.62", options: { color: NAVY, bold: true, fontSize: 12, align: "center" } },
      { text: "+0.29", options: { color: SUCCESS, bold: true, fontSize: 12, align: "center" } },
    ],
    [
      { text: "Max drawdown", options: { color: SLATE, fontSize: 12 } },
      { text: "-19.15%", options: { color: SLATE, fontSize: 12, align: "center" } },
      { text: "-25.10%", options: { color: SLATE, fontSize: 12, align: "center" } },
      { text: "-5.95 pp", options: { color: AMBER, fontSize: 12, align: "center" } },
    ],
  ];

  s.addTable(gateData, {
    x: MX, y: 1.95, w: W - 2 * MX, colW: [2.3, 2.2, 2.2, 2.2],
    border: { type: "solid", pt: 0.5, color: RULE },
    fontFace: "Calibri",
    rowH: [0.4, 0.45, 0.45, 0.45, 0.45],
    fill: { color: "FFFFFF" },
  });

  // Walk-forward callout
  s.addShape(pres.shapes.RECTANGLE, { x: MX, y: 4.4, w: W - 2 * MX, h: 0.85, fill: { color: NAVY }, line: { type: "none" } });
  s.addShape(pres.shapes.RECTANGLE, { x: MX, y: 4.4, w: 0.08, h: 0.85, fill: { color: ACCENT }, line: { type: "none" } });
  s.addText([
    { text: "WALK-FORWARD ACROSS 6 OOS WINDOWS  ·  ", options: { color: ACCENT, charSpacing: 3, bold: true, fontSize: 10 } },
    { text: "mean +11.6 pp CAGR lift  ·  4 of 6 windows promote (67%)  ·  reproduce via scripts/walk_forward_gate.py", options: { color: "FFFFFF", fontSize: 11 } },
  ], { x: MX + 0.25, y: 4.4, w: W - 2 * MX - 0.4, h: 0.85, fontFace: "Calibri", valign: "middle", margin: 0 });

  footer(s, 6, TOTAL);
  s.addNotes(
    "Pause on this slide. These aren't backtests we cherry-picked — they're verified by " +
    "scripts/walk_forward_gate.py in the public repo. Anyone can clone and reproduce. " +
    "That reproducibility is the moat."
  );
}

// === Slide 8: HONEST LOSSES =============================================
{
  const s = pres.addSlide();
  s.background = { color: PAPER };
  slideTitle(s, "Slide 7 of 11  ·  Honesty", "The 2 windows where MLA lost");

  s.addText("Most demos hide losses. We documented them.", {
    x: MX, y: 1.55, w: W - 2 * MX, h: 0.3,
    fontSize: 12, italic: true, color: SLATE, fontFace: "Calibri", margin: 0,
  });

  const lossData = [
    [
      { text: "WINDOW", options: { bold: true, color: "FFFFFF", fill: { color: NAVY }, fontSize: 10 } },
      { text: "RBA", options: { bold: true, color: "FFFFFF", fill: { color: NAVY }, fontSize: 10, align: "center" } },
      { text: "MLA-7", options: { bold: true, color: "FFFFFF", fill: { color: NAVY }, fontSize: 10, align: "center" } },
      { text: "LIFT", options: { bold: true, color: "FFFFFF", fill: { color: NAVY }, fontSize: 10, align: "center" } },
      { text: "OUTCOME", options: { bold: true, color: "FFFFFF", fill: { color: NAVY }, fontSize: 10, align: "center" } },
    ],
    [
      { text: "2021-H1  bull leg", options: { fontSize: 11, color: NAVY } },
      { text: "+79%", options: { fontSize: 11, color: SLATE, align: "center" } },
      { text: "+55%", options: { fontSize: 11, color: SLATE, align: "center" } },
      { text: "-24 pp", options: { fontSize: 11, bold: true, color: DANGER, align: "center" } },
      { text: "MLA loss", options: { fontSize: 11, color: DANGER, align: "center" } },
    ],
    [
      { text: "2021-H2  peak", options: { fontSize: 11, color: NAVY } },
      { text: "+56%", options: { fontSize: 11, color: SLATE, align: "center" } },
      { text: "+72%", options: { fontSize: 11, color: SLATE, align: "center" } },
      { text: "+16 pp", options: { fontSize: 11, bold: true, color: SUCCESS, align: "center" } },
      { text: "MLA win", options: { fontSize: 11, color: SUCCESS, align: "center" } },
    ],
    [
      { text: "2022-H1  rate shock", options: { fontSize: 11, color: NAVY } },
      { text: "-16%", options: { fontSize: 11, color: SLATE, align: "center" } },
      { text: "-23%", options: { fontSize: 11, color: SLATE, align: "center" } },
      { text: "-7 pp", options: { fontSize: 11, color: DANGER, align: "center" } },
      { text: "MLA loss", options: { fontSize: 11, color: DANGER, align: "center" } },
    ],
    [
      { text: "2022-H2  capitulation", options: { fontSize: 11, color: NAVY } },
      { text: "+34%", options: { fontSize: 11, color: SLATE, align: "center" } },
      { text: "+20%", options: { fontSize: 11, color: SLATE, align: "center" } },
      { text: "-14 pp", options: { fontSize: 11, color: DANGER, align: "center" } },
      { text: "MLA loss", options: { fontSize: 11, color: DANGER, align: "center" } },
    ],
    [
      { text: "2023-H1  bottom-bounce", options: { fontSize: 11, color: NAVY } },
      { text: "+25%", options: { fontSize: 11, color: SLATE, align: "center" } },
      { text: "+87%", options: { fontSize: 11, color: SLATE, align: "center" } },
      { text: "+51 pp", options: { fontSize: 11, bold: true, color: SUCCESS, align: "center" } },
      { text: "MLA win", options: { fontSize: 11, color: SUCCESS, align: "center" } },
    ],
    [
      { text: "2023-H2  AI rally", options: { fontSize: 11, color: NAVY } },
      { text: "+13%", options: { fontSize: 11, color: SLATE, align: "center" } },
      { text: "+25%", options: { fontSize: 11, color: SLATE, align: "center" } },
      { text: "+14 pp", options: { fontSize: 11, color: SUCCESS, align: "center" } },
      { text: "MLA win", options: { fontSize: 11, color: SUCCESS, align: "center" } },
    ],
  ];

  s.addTable(lossData, {
    x: MX, y: 2.0, w: W - 2 * MX, colW: [2.6, 1.4, 1.4, 1.4, 2.1],
    border: { type: "solid", pt: 0.5, color: RULE },
    fontFace: "Calibri",
    rowH: [0.38, ...Array(6).fill(0.32)],
    fill: { color: "FFFFFF" },
  });

  s.addText([
    { text: "Across a year, wins compound. ", options: { bold: true, color: NAVY } },
    { text: "On a single quarter, ~1-in-3 chance of underperforming. We tell you. ", options: { color: SLATE } },
    { text: "That's the institutional standard, now free.", options: { italic: true, color: TRUST } },
  ], {
    x: MX, y: 4.65, w: W - 2 * MX, h: 0.55,
    fontSize: 12, fontFace: "Calibri", align: "center", margin: 0,
  });

  footer(s, 7, TOTAL);
  s.addNotes(
    "Lean into this. Tell the audience: 'If you trust a tool that claims a model never loses, you're being " +
    "sold something. We tell you exactly when ours did. That's the institutional standard, and now it's free.'"
  );
}

// === Slide 9: IMPACT ====================================================
{
  const s = pres.addSlide();
  s.background = { color: PAPER };
  slideTitle(s, "Slide 8 of 11  ·  Impact", "Why this matters — measurable outcomes");

  // Three-column impact panel
  const cards = [
    {
      head: "RETAIL",
      stat: "RM 90B",
      sub: "Malaysian retail trading turnover (2024)",
      body: "Most participants use chat groups. TRIO Web: free, transparent, auditable, no signal-service pitch.",
      color: ACCENT,
    },
    {
      head: "INSTITUTIONAL",
      stat: "$30k–100k",
      sub: "per analyst per year on Bloomberg/FactSet",
      body: "BYOK lets institutions plug existing keys into open-source frontend. Marginal cost: zero.",
      color: TRUST,
    },
    {
      head: "B2B PIPELINE",
      stat: "$5k–25k/yr",
      sub: "per private deployment",
      body: "Family offices, boutique funds, robo-advisors. One contract pays for the project's first year.",
      color: SUCCESS,
    },
  ];

  const cy = 1.65;
  const ch = 3.4;
  const cardW = 2.95;
  const gap = 0.22;
  const startX = MX;

  cards.forEach((c, i) => {
    const cx = startX + i * (cardW + gap);
    s.addShape(pres.shapes.RECTANGLE, { x: cx, y: cy, w: cardW, h: ch, fill: { color: "FFFFFF" }, line: { color: RULE, width: 0.5 } });
    s.addShape(pres.shapes.RECTANGLE, { x: cx, y: cy, w: cardW, h: 0.55, fill: { color: NAVY }, line: { type: "none" } });
    s.addText(c.head, { x: cx, y: cy, w: cardW, h: 0.55, fontSize: 11, bold: true, color: c.color, charSpacing: 5, fontFace: "Calibri", align: "center", valign: "middle", margin: 0 });

    s.addText(c.stat, { x: cx, y: cy + 0.85, w: cardW, h: 0.85, fontSize: 38, bold: true, color: NAVY, fontFace: "Calibri", align: "center", margin: 0 });
    s.addText(c.sub, { x: cx + 0.2, y: cy + 1.7, w: cardW - 0.4, h: 0.45, fontSize: 10, italic: true, color: MUTED, fontFace: "Calibri", align: "center", margin: 0 });

    s.addShape(pres.shapes.LINE, { x: cx + 0.6, y: cy + 2.25, w: cardW - 1.2, h: 0, line: { color: RULE, width: 0.75 } });
    s.addText(c.body, { x: cx + 0.2, y: cy + 2.4, w: cardW - 0.4, h: ch - 2.5, fontSize: 11, color: SLATE, fontFace: "Calibri", margin: 0, valign: "top" });
  });

  footer(s, 8, TOTAL);
  s.addNotes(
    "Pick one number per audience. To retail traders: 'free.' To institutional: 'your existing Bloomberg key, " +
    "but the analysis is auditable.' To engineers / B2B prospects: 'this is how you build a factor model.'"
  );
}

// === Slide 10: ROADMAP ==================================================
{
  const s = pres.addSlide();
  s.background = { color: PAPER };
  slideTitle(s, "Slide 9 of 11  ·  Roadmap", "Already 70% built");

  const phases = [
    { p: "P0–P3", t: "Core scoring + 4 RBA engines + 4 data providers", st: "shipped" },
    { p: "P4",     t: "Backtester + walk-forward harness", st: "shipped" },
    { p: "P5",     t: "PIT pipeline + MLA + promotion gate", st: "shipped" },
    { p: "P6",     t: "Universe expansion + BYOK + public repo + CI", st: "shipped" },
    { p: "Next",   t: "Live deploy (Render + Vercel, ~10 min)",        st: "ready" },
    { p: "Then",   t: "13F-HR · Bursa scraper for KLCI · MIROFISH swarm-sim",   st: "queued" },
  ];

  const baseY = 1.7;
  const rowH = 0.55;

  phases.forEach((p, i) => {
    const y = baseY + i * rowH;
    const bg = (i % 2 === 0) ? "FFFFFF" : PAPER;
    s.addShape(pres.shapes.RECTANGLE, { x: MX, y: y, w: W - 2 * MX, h: rowH, fill: { color: bg }, line: { color: RULE, width: 0.5 } });

    // Phase tag
    const tagColor = (p.st === "shipped") ? SUCCESS : (p.st === "ready") ? AMBER : MUTED;
    s.addShape(pres.shapes.RECTANGLE, { x: MX, y: y, w: 1.0, h: rowH, fill: { color: tagColor }, line: { type: "none" } });
    s.addText(p.p, { x: MX, y: y, w: 1.0, h: rowH, fontSize: 13, bold: true, color: "FFFFFF", fontFace: "Calibri", align: "center", valign: "middle", margin: 0 });

    s.addText(p.t, { x: MX + 1.2, y: y, w: W - 2 * MX - 1.7, h: rowH, fontSize: 12, color: NAVY, fontFace: "Calibri", valign: "middle", margin: 0 });

    // Status badge on right
    const badgeText = p.st === "shipped" ? "✓ SHIPPED" : p.st === "ready" ? "READY" : "QUEUED";
    const badgeColor = p.st === "shipped" ? SUCCESS : p.st === "ready" ? AMBER : MUTED;
    s.addText(badgeText, { x: W - MX - 1.3, y: y, w: 1.3, h: rowH, fontSize: 10, bold: true, color: badgeColor, charSpacing: 3, fontFace: "Calibri", align: "right", valign: "middle", margin: 0 });
  });

  s.addText("Cycle time from concept to gate-passed result: 3 working days. Every commit on public main.", {
    x: MX, y: 5.05, w: W - 2 * MX, h: 0.3,
    fontSize: 11, italic: true, color: MUTED, fontFace: "Calibri", align: "center", margin: 0,
  });

  footer(s, 9, TOTAL);
  s.addNotes(
    "This isn't a 'we're going to build it' pitch. It's a 'we already built it, here's where we go next.' " +
    "The roadmap exists to show the team can execute AND to size the B2B opportunity."
  );
}

// === Slide 11: ASK ======================================================
{
  const s = pres.addSlide();
  s.background = { color: PAPER };
  slideTitle(s, "Slide 10 of 11  ·  Ask", "The ask");

  const asks = [
    { who: "HACKATHON JUDGES", what: "Score against the rubric — appendix maps each criterion to slides.", icon: "1" },
    { who: "INSTITUTIONAL PARTNERS", what: "30-minute call. Bring a universe + date range. We run a walk-forward gate live.", icon: "2" },
    { who: "DEVELOPERS", what: "Star, fork, contribute.  github.com/silattrader/trio-web", icon: "3" },
    { who: "HIRING MARKET", what: "Open to quant / quant-eng / ML-platform roles. 3 days · gate-passed ML · public.", icon: "4" },
  ];

  const baseY = 1.7;
  const rowH = 0.75;

  asks.forEach((a, i) => {
    const y = baseY + i * (rowH + 0.1);
    s.addShape(pres.shapes.RECTANGLE, { x: MX, y: y, w: W - 2 * MX, h: rowH, fill: { color: "FFFFFF" }, line: { color: RULE, width: 0.5 } });

    // Number circle
    s.addShape(pres.shapes.OVAL, { x: MX + 0.2, y: y + 0.16, w: 0.43, h: 0.43, fill: { color: TRUST }, line: { type: "none" } });
    s.addText(a.icon, { x: MX + 0.2, y: y + 0.16, w: 0.43, h: 0.43, fontSize: 16, bold: true, color: "FFFFFF", fontFace: "Calibri", align: "center", valign: "middle", margin: 0 });

    s.addText(a.who, { x: MX + 0.85, y: y + 0.07, w: W - 2 * MX - 1.0, h: 0.3, fontSize: 11, bold: true, color: TRUST, charSpacing: 4, fontFace: "Calibri", margin: 0 });
    s.addText(a.what, { x: MX + 0.85, y: y + 0.35, w: W - 2 * MX - 1.0, h: rowH - 0.4, fontSize: 12, color: NAVY, fontFace: "Calibri", margin: 0, valign: "top" });
  });

  footer(s, 10, TOTAL);
  s.addNotes(
    "Three asks, four audiences, one slide. Don't try to convert everyone with the same call to action."
  );
}

// === Slide 12: CLOSE ====================================================
{
  const s = pres.addSlide();
  s.background = { color: NAVY };

  // Accent strip on left
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.18, h: H, fill: { color: TRUST }, line: { type: "none" } });

  s.addText("THANK YOU", {
    x: 0.7, y: 0.7, w: 8, h: 0.4, fontSize: 12, color: ACCENT, charSpacing: 8, bold: true, fontFace: "Calibri",
  });

  s.addText("Research, not advice.\nThat's a feature.", {
    x: 0.7, y: 1.4, w: 9, h: 1.8, fontSize: 44, bold: true, color: "FFFFFF", fontFace: "Calibri", paraSpaceAfter: 4,
  });

  s.addShape(pres.shapes.RECTANGLE, { x: 0.7, y: 3.3, w: 1.5, h: 0.04, fill: { color: ACCENT }, line: { type: "none" } });

  s.addText([
    { text: "TRIO Web is research and decision-support tooling. Not licensed investment advice.", options: { breakLine: true, fontSize: 13, color: "CBD5E1" } },
    { text: "Output is opinion derived from public-domain factor models on publicly-available data.", options: { breakLine: true, fontSize: 13, color: "CBD5E1" } },
    { text: "", options: { breakLine: true, fontSize: 8 } },
    { text: "We chose this positioning deliberately — open, free, transparent, auditable, fork-able.", options: { italic: true, fontSize: 13, color: ACCENT } },
  ], { x: 0.7, y: 3.5, w: 9, h: 1.5, fontFace: "Calibri" });

  s.addText("github.com/silattrader/trio-web   ·   silattrader@gmail.com", {
    x: 0.7, y: H - 0.6, w: 9, h: 0.3, fontSize: 12, color: MUTED, fontFace: "Calibri", margin: 0,
  });

  s.addNotes(
    "Close warmly. Thank the panel. The disclaimer slide turns a legal nicety into a positioning statement."
  );
}

// --- Write file -----------------------------------------------------------
pres.writeFile({ fileName: "C:/Users/User/trio-web/docs/PITCH.pptx" })
  .then(fileName => console.log("Wrote " + fileName))
  .catch(err => { console.error(err); process.exit(1); });
