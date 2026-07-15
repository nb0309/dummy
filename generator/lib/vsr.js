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
 * WCAG 4.1.3 interaction probe. Start the reader on the whole page, drive the
 * status update, and report what the reader announced. The virtual reader's
 * internal MutationObserver turns a *live-region* change into a spoken-phrase-log
 * entry formatted "polite: …" / "assertive: …"; a bare element or an
 * aria-live="off" region stays SILENT. We return only the new live-region
 * announcements (or [] when silent), which is exactly the 4.1.3 pass/fail signal.
 *
 * Two ways to drive the update:
 *  - `[data-status-trigger]` present -> click it and let the page's own handler
 *    write the status. This is the real code path, so the fixture's message must
 *    NOT be pre-rendered: 4.1.3 is about a message *added or changed* after load,
 *    and a live region announces changes, never its initial content.
 *  - no trigger -> replay the region's existing text (clear -> tick -> re-insert)
 *    as a synthetic mutation. Fixtures in `tests/wcag 4.1.3` are static markup
 *    with no control to click, so the probe has to supply the change itself.
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
      const isLive = (p) => /^(polite|assertive):/i.test(p || "");

      // Is the region pruned from the accessibility tree? The virtual reader's
      // static walk honours this, but its live-region path does NOT: it will
      // happily announce a mutation inside a display:none subtree, which no real
      // screen reader does. Evaluated AFTER the update so the common "hidden
      // until needed, then revealed and filled" pattern still reads as announced.
      const hiddenFromAt = (el) => {
        if (!el.isConnected) return true;
        for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
          if (n.hasAttribute("hidden")) return true;
          if (n.getAttribute("aria-hidden") === "true") return true;
          const cs = getComputedStyle(n);
          // display must be checked per-ancestor: an element inside a
          // display:none subtree still reports its own specified display.
          if (cs.display === "none") return true;
          if (cs.visibility === "hidden" || cs.visibility === "collapse") return true;
        }
        return false;
      };

      const v = new mod.Virtual();
      await v.start({ container: document.body });
      const before = (await v.spokenPhraseLog()).length;

      const trigger = document.querySelector("[data-status-trigger]");
      if (trigger) {
        trigger.click();
      } else {
        const text = target.textContent;
        target.textContent = "";
        await tick();
        target.textContent = text;
      }

      // The announcement is queued on a MutationObserver microtask (after an
      // internal `await tick()`), so poll until a live-region phrase lands or we
      // time out. Poll on the *filtered* result, not the raw log length: a click
      // can push unrelated phrases (focus moves, etc.) that would otherwise end
      // the wait before the announcement arrives.
      const deadline = Date.now() + maxWaitMs;
      let spoken = (await v.spokenPhraseLog()).slice(before).filter(isLive);
      while (spoken.length === 0 && Date.now() < deadline) {
        await sleep(50);
        spoken = (await v.spokenPhraseLog()).slice(before).filter(isLive);
      }
      await v.stop();

      return hiddenFromAt(target) ? [] : spoken;
    },
    { maxWaitMs }
  );
}
