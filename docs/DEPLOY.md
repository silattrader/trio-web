# Deploying TRIO Web

Two services, two providers, ~10 minutes if everything connects on first try.

> **Pre-deploy verification (run 2026-04-27):** the exact build commands
> in `render.yaml` were executed in a fresh Python 3.12 venv and produced
> a working API. The full Next.js production build was tested end-to-end
> proxying to the API. Both succeed without errors. Findings baked into
> the steps below — including one gotcha: Vercel's `NEXT_PUBLIC_API_URL`
> must be set **before** clicking Deploy (it's a build-time variable).

| Component | Provider | Free? | Cold-start? |
|-----------|----------|-------|-------------|
| Next.js (web UI) | [Vercel](https://vercel.com) | Yes | None — always warm |
| FastAPI (scoring) | [Render](https://render.com) | Yes | ~30s after 15 min idle |

Total cost on free tiers: **$0/month**. You'll outgrow the free Render
tier (512 MB / 0.1 CPU) under sustained traffic; bump to Starter ($7/mo)
when that happens.

## 1. Deploy the API to Render

1. Sign up at [render.com](https://render.com) (GitHub OAuth works).
2. Dashboard → **New → Blueprint**.
3. Connect repository: `silattrader/trio-web`.
4. Render reads `render.yaml` from the repo root and proposes the
   `trio-api` service. Click **Apply**.
5. First build takes ~3-5 min (compiles numpy, scikit-learn, etc.).
6. Once status is `live`, copy the public URL — looks like
   `https://trio-api-xxxx.onrender.com`. Test it:
   ```
   curl https://trio-api-xxxx.onrender.com/health
   {"status":"ok"}
   ```

### Recommended env vars (Render dashboard → trio-api → Environment)

```
TRIO_SEC_UA   = Mailto silattrader@gmail.com
TRIO_WIKI_UA  = Mailto silattrader@gmail.com
```

**Why?** SEC and Wikimedia rate-limit empty user-agents. Setting these
gives anonymous demo-mode visitors a fallback UA so SEC/Wiki don't 429
their backtest.

`TRIO_FMP_KEY` is **optional** — only set it if you want to let
anonymous visitors trigger FMP-backed live scoring on your quota. Most
portfolio demos skip this; visitors who want live scoring paste their
own keys via the BYOK panel.

## 2. Deploy the web UI to Vercel

1. Sign up at [vercel.com](https://vercel.com) (GitHub OAuth works).
2. Dashboard → **Add New → Project**.
3. Import `silattrader/trio-web`.
4. **Root Directory:** `apps/web` (Vercel won't auto-detect because of
   the monorepo layout).
5. **Build & Output Settings:** leave Vercel's defaults. The `vercel.json`
   in `apps/web` adds security headers automatically.
6. **Environment Variables** → add **before** clicking Deploy:
   ```
   NEXT_PUBLIC_API_URL = https://trio-api-xxxx.onrender.com
   ```
   Use the Render URL from step 1.6 (no trailing slash).

   ⚠ **Order matters**: this variable is read at *build time* by Next.js's
   rewrite config. If you click Deploy before adding it, Next.js will bake
   in the localhost fallback and `/api/*` will 404 in production.
   You'd have to redeploy from the Vercel dashboard after setting the var.
7. Click **Deploy**. Build runs in ~1-2 min.
8. Visit the deployed URL — Vercel hands you a `*.vercel.app` subdomain
   you can use straight away.

## 3. Verify end-to-end

1. Open the deployed Vercel URL.
2. The home page loads with a "BYOK · demo mode" badge in the header.
3. Click **Try sample** in the upload card → 8 KLCI tickers score with
   BOS in <1 second. (No API keys needed for this path.)
4. Try **Live universe → yfinance → Fetch & score** with default tickers.
   This call goes browser → Vercel → Render API → yfinance → back. Confirms
   the API and its dependencies are reachable.
5. Open the BYOK panel in the header. Paste a SEC UA + Wiki UA + (optional)
   FMP key. Save. Run the backtest with `strategy=rba_pit`. PIT data flows
   through and appears in the equity curve.

## 4. Custom domain (optional)

- Vercel: Settings → Domains → Add `trio-web.io`. Follow DNS instructions.
- Render: Settings → Custom Domain → Add `api.trio-web.io`. Update
  Vercel's `NEXT_PUBLIC_API_URL` to the new domain.
- Both providers do free TLS via Let's Encrypt.

## Operational notes

- **Render free tier sleeps after 15 minutes of no traffic.** First request
  after sleep takes ~30 seconds while Python re-warms. The browser will
  show a spinner; consider a "warming up" message if you see this in
  user research.
- **First-time PIT fetches build a cache.** Render's filesystem is
  ephemeral — restarts wipe the cache. For a portfolio demo this is fine.
  For real production, attach a persistent disk ($1/mo on Render) and
  point `TRIO_EDGAR_CACHE`, `TRIO_FMP_CACHE`, `TRIO_WIKI_UA` at it.
- **Cold-MLA-load.** First `/score?model=mla_v0` after a Render restart
  loads the joblib artifact and may take 1-2s extra. Subsequent calls
  are instant.

## Self-hosting

The repo also runs as a single-machine setup with `make install && make run`
+ `cd apps/web && npm run dev`. Useful when you want to keep your API
keys entirely off any hosted infrastructure.
