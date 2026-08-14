#!/usr/bin/env node
/**
 * Real automated WCAG 2.1 AA accessibility scan — not a lint rule, an
 * actual browser (Chromium via Playwright) rendering every listed route
 * against a running instance of this app, with axe-core auditing the
 * live DOM in both the light and dark theme.
 *
 * Usage:
 *   1. Have the backend running (real Postgres/Redis) and reachable.
 *   2. npm run build && npm start   (a dev server also works, but a
 *      production build is what the scan should represent)
 *   3. Register a real account and export its tokens as env vars, e.g.:
 *        ACCESS_TOKEN=... REFRESH_TOKEN=... node scripts/a11y-scan.mjs
 *      Authenticated routes are skipped (with a note) if these are unset.
 *
 * Exits non-zero if any violation is found, so this can be wired into CI
 * once a real backend + built app is available in that environment.
 */
import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";

const BASE_URL = process.env.A11Y_SCAN_BASE_URL || "http://127.0.0.1:3000";
const OUT_FILE = process.env.A11Y_SCAN_OUT || "/tmp/a11y-results.json";

const PUBLIC_PAGES = [
  "/", "/login", "/register", "/forgot-password", "/courses", "/leaderboard",
  "/contests", "/contests/certificates/verify", "/certificates/verify", "/search",
];
const AUTH_PAGES = [
  "/dashboard", "/settings", "/profile", "/notifications", "/quiz-history",
  "/timetable", "/practice", "/ai-assistant", "/certificates/me",
  "/contests/certificates", "/chat", "/discussions",
];

const { ACCESS_TOKEN, REFRESH_TOKEN } = process.env;

const browser = await chromium.launch();
const results = [];

async function scanPage(page, path, themeLabel) {
  try {
    await page.goto(`${BASE_URL}${path}`, { waitUntil: "networkidle", timeout: 15000 });
  } catch {
    await page.goto(`${BASE_URL}${path}`, { waitUntil: "load", timeout: 15000 }).catch(() => {});
  }
  await page.waitForTimeout(500);
  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  results.push({ path, theme: themeLabel, violations: axe.violations });
  console.log(`[${themeLabel}] ${path}: ${axe.violations.length} violation type(s)`);
}

for (const theme of ["light", "dark"]) {
  const publicCtx = await browser.newContext();
  const publicPage = await publicCtx.newPage();
  await publicPage.goto(BASE_URL, { waitUntil: "load" });
  await publicPage.evaluate((t) => window.localStorage.setItem("ss-theme", t), theme);
  for (const path of PUBLIC_PAGES) {
    await scanPage(publicPage, path, theme);
  }
  await publicCtx.close();

  if (ACCESS_TOKEN && REFRESH_TOKEN) {
    const authCtx = await browser.newContext();
    const authPage = await authCtx.newPage();
    await authPage.goto(BASE_URL, { waitUntil: "load" });
    await authPage.evaluate(({ access, refresh, t }) => {
      window.localStorage.setItem("ss_access_token", access);
      window.localStorage.setItem("ss_refresh_token", refresh);
      window.localStorage.setItem("ss-theme", t);
    }, { access: ACCESS_TOKEN, refresh: REFRESH_TOKEN, t: theme });
    for (const path of AUTH_PAGES) {
      await scanPage(authPage, path, theme);
    }
    await authCtx.close();
  } else if (theme === "light") {
    console.log("(skipping authenticated routes — set ACCESS_TOKEN/REFRESH_TOKEN env vars to include them)");
  }
}

await browser.close();

fs.writeFileSync(OUT_FILE, JSON.stringify(results, null, 2));

let totalViolations = 0;
const bySeverity = {};
for (const r of results) {
  for (const v of r.violations) {
    totalViolations++;
    bySeverity[v.impact] = (bySeverity[v.impact] || 0) + 1;
  }
}
console.log("\n=== SUMMARY ===");
console.log("total violation types across all pages/themes:", totalViolations);
console.log("by impact:", bySeverity);
console.log(`full detail written to ${OUT_FILE}`);

process.exit(totalViolations > 0 ? 1 : 0);
