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

export const pageReadingOrder = (page) => traverse(page, { maxSteps: 400 });
export const elementTranscript = (page, sampleId) => traverse(page, { sampleId, maxSteps: 250 });
