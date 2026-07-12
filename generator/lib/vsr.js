// Drive the @guidepup/virtual-screen-reader inside the page. The browser bundle
// (self-contained ESM exporting { Virtual, virtual }) is loaded once per page via
// a Blob dynamic import(); traversals then run entirely in-page and return the
// spoken-phrase transcript. No real screen reader, no OS focus, deterministic.

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

// Resolve the package location robustly (it may live in a node_modules folder
// several directories up, e.g. the shared d2/node_modules) rather than assuming
// it sits next to this file.
const require = createRequire(import.meta.url);
const pkgJson = require.resolve("@guidepup/virtual-screen-reader/package.json");
const BUNDLE = fs.readFileSync(
  path.join(path.dirname(pkgJson), "lib", "esm", "index.browser.js"),
  "utf8"
);

/** Load the virtual-screen-reader module into the page (idempotent). */
export async function injectVsr(page) {
  await page.evaluate(async (code) => {
    if (window.__vsrMod) return;
    const blob = new Blob([code], { type: "text/javascript" });
    const u = URL.createObjectURL(blob);
    try {
      window.__vsrMod = await import(u);
    } finally {
      URL.revokeObjectURL(u);
    }
  }, BUNDLE);
}

/**
 * Walk the virtual screen reader forward and return the ordered spoken phrases.
 * Scope is the whole page (sampleId null) or a single element (its
 * data-sample-id), which gives an accurate per-element transcript.
 *
 * @param {import('@playwright/test').Page} page
 * @param {{sampleId?: string|null, maxSteps?: number}} opts
 * @returns {Promise<string[]>}
 */
export async function traverse(page, { sampleId = null, maxSteps = 300 } = {}) {
  return page.evaluate(
    async ({ sampleId, maxSteps }) => {
      const { Virtual } = window.__vsrMod;
      const container = sampleId
        ? document.querySelector(`[data-sample-id="${sampleId}"]`)
        : document.body;
      if (!container) return [];

      const v = new Virtual();
      await v.start({ container });

      const phrases = [];
      const first = await v.lastSpokenPhrase();
      if (first) phrases.push(first);

      let prev = first;
      let repeat = 0;
      for (let i = 0; i < maxSteps; i++) {
        await v.next();
        const p = await v.lastSpokenPhrase();
        // The reader cycles: after the container's closing "end of …" it wraps
        // back to the opening phrase. Break only on that true wrap (opening
        // phrase returns AND the previous phrase was an "end of …" boundary) so
        // nested same-role elements (a <ul> inside a <ul>, both "list") don't
        // trigger a false stop.
        if (phrases.length && p === phrases[0] && /^end of\b/i.test(prev || "")) break;
        // Safety net for a single-node container that just re-announces itself.
        if (p === prev) {
          if (++repeat >= 2) break;
        } else {
          repeat = 0;
        }
        phrases.push(p);
        prev = p;
      }
      await v.stop();

      // trim any trailing repeats left by the safety net
      while (phrases.length >= 2 && phrases[phrases.length - 1] === phrases[phrases.length - 2]) {
        phrases.pop();
      }
      return phrases;
    },
    { sampleId, maxSteps }
  );
}

export const elementTranscript = (page, sampleId) => traverse(page, { sampleId, maxSteps: 250 });

/**
 * WCAG 4.1.3 interaction probe. Start the reader on the whole page, then simulate
 * a status update by mutating the fixture-marked `[data-status-target]` element
 * (clear -> tick -> re-insert its text). The virtual reader's internal
 * MutationObserver turns a *live-region* change into a spoken-phrase-log entry
 * formatted "polite: …" / "assertive: …"; a bare element, an aria-live="off"
 * region, or a display:none/aria-hidden region stays SILENT. We return only the
 * new live-region announcements (or [] when silent), which is exactly the 4.1.3
 * pass/fail signal.
 *
 * Returns `null` when the page has no `[data-status-target]` (not a status page,
 * so the row's feature is N/A), `[]` when a target was updated but nothing was
 * announced (the 4.1.3 failure), or the announcement phrases when it spoke.
 *
 * @param {import('@playwright/test').Page} page
 * @param {{maxWaitMs?: number}} opts
 * @returns {Promise<string[]|null>} announcements, [] if silent, or null if N/A
 */
export async function statusAnnouncementProbe(page, { maxWaitMs = 2000 } = {}) {
  return page.evaluate(
    async ({ maxWaitMs }) => {
      const mod = window.__vsrMod;
      const target = document.querySelector("[data-status-target]");
      if (!mod || !target) return null;

      const tick = () => new Promise((r) => setTimeout(r, 0));
      const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

      const v = new mod.Virtual();
      await v.start({ container: document.body });
      const before = (await v.spokenPhraseLog()).length;

      // Simulate the status changing: clear, let the observer flush, then
      // re-insert the original text -> a genuine mutation inside the region.
      const text = target.textContent;
      target.textContent = "";
      await tick();
      target.textContent = text;

      // The announcement is queued on a MutationObserver microtask (after an
      // internal `await tick()`), so poll the log until it grows or we time out.
      const deadline = Date.now() + maxWaitMs;
      let log = await v.spokenPhraseLog();
      while (log.length === before && Date.now() < deadline) {
        await sleep(50);
        log = await v.spokenPhraseLog();
      }
      await v.stop();

      return log.slice(before).filter((p) => /^(polite|assertive):/i.test(p || ""));
    },
    { maxWaitMs }
  );
}
