// Wait until a page is actually capturable. `load` only means the parser
// finished; IntersectionObserver / infinite-scroll / loading="lazy" content
// often has not been requested yet. Scrolling the document is what those
// loaders listen for. After revealing, we return to the top so Tab sweeps and
// document-relative geometry still start from a known origin.
//
// Bounded: a feed that never stops growing is cut off by maxSteps / maxMs.
// Short fixture pages (no overflow, no growth) pay one or two pause intervals.

import { waitForChildFrames } from "./frames.js";

/**
 * @param {import('@playwright/test').Page} page
 * @param {{
 *   pauseMs?: number,
 *   maxSteps?: number,
 *   stableRounds?: number,
 *   maxMs?: number,
 *   networkIdleMs?: number,
 * }} [opts]
 */
export async function settlePage(
  page,
  {
    pauseMs = 150,
    maxSteps = 30,
    stableRounds = 2,
    maxMs = 8000,
    networkIdleMs = 1200,
  } = {}
) {
  // SPAs often fetch after `load`. Do not require idle — analytics keep many
  // sites busy forever — but take it if it arrives quickly.
  await page.waitForLoadState("networkidle", { timeout: networkIdleMs }).catch(() => {});

  await page.evaluate(
    async ({ pauseMs, maxSteps, stableRounds, maxMs }) => {
      const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
      const docHeight = () =>
        Math.max(
          document.body ? document.body.scrollHeight : 0,
          document.documentElement ? document.documentElement.scrollHeight : 0
        );

      const started = Date.now();
      const view = window.innerHeight || 600;
      const step = Math.max(1, Math.round(view * 0.85));
      let lastHeight = docHeight();
      let stable = 0;

      for (let i = 0; i < maxSteps && Date.now() - started < maxMs; i++) {
        const bottom = docHeight();
        window.scrollTo(0, Math.min(bottom, window.scrollY + step));
        await sleep(pauseMs);

        const now = docHeight();
        const atBottom = window.scrollY + view >= now - 4;
        if (now <= lastHeight + 4 && atBottom) {
          if (++stable >= stableRounds) break;
        } else {
          stable = 0;
          lastHeight = now;
        }
      }

      window.scrollTo(0, 0);
      await sleep(50);
    },
    { pauseMs, maxSteps, stableRounds, maxMs }
  );

  await waitForChildFrames(page);
}

/**
 * Navigate, then reveal scroll-triggered content before the caller reads the DOM.
 *
 * @param {import('@playwright/test').Page} page
 * @param {string} url
 * @param {Parameters<typeof settlePage>[1]} [opts]
 */
export async function gotoAndSettle(page, url, opts) {
  await page.goto(url, { waitUntil: "load" });
  await settlePage(page, opts);
}
