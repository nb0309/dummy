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

/**
 * WCAG 4.1.2 interaction probe. Reads the element's role/name/state as
 * announced BEFORE any interaction, clicks it (or its `[data-role-trigger]`
 * descendant), then reads it again AFTER. Returning both the spoken phrase
 * and the raw outerHTML lets the skill catch the defect a static transcript
 * alone cannot show: a control whose CSS class / visual state flips on click
 * while `phrase` stays identical proves the state change never reached the
 * accessibility tree, even though something visibly happened.
 *
 * Caller decides whether to invoke this at all -- extract.js's `control`
 * classification is the single source of truth for which samples qualify, so
 * this function does not re-derive that selector. It only self-gates on the
 * sample existing.
 *
 * @param {import('@playwright/test').Page} page
 * @param {string} sampleId
 * @param {{settleMs?: number}} opts
 * @returns {Promise<{before: {phrase: string, html: string}, after: {phrase: string, html: string}}|null>}
 */
export async function roleStateValueProbe(page, sampleId, { settleMs = 50 } = {}) {
  return page.evaluate(
    async ({ sampleId, settleMs }) => {
      const mod = window.__vsrMod;
      const container = document.querySelector(`[data-sample-id="${sampleId}"]`);
      if (!mod || !container) return null;

      const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

      const read = async () => {
        const v = new mod.Virtual();
        await v.start({ container });
        const phrase = (await v.lastSpokenPhrase()) || "";
        await v.stop();
        return { phrase, html: container.outerHTML };
      };

      const before = await read();

      const trigger = container.matches("[data-role-trigger]")
        ? container
        : container.querySelector("[data-role-trigger]") || container;
      trigger.click();
      await sleep(settleMs);

      // For a native <input type="checkbox"|"radio">, click() toggles the live
      // `.checked` IDL property, but the virtual reader's accessible-state
      // computation reads the `checked` content ATTRIBUTE (which the browser
      // does not keep in sync with the property). Mirror it across, the same
      // trick lib/interact.js uses for `.value` -- otherwise every native
      // checkbox/radio would read as silently unchanged by this probe
      // regardless of whether it actually is.
      if (container.matches("input[type='checkbox'], input[type='radio']")) {
        if (container.checked) container.setAttribute("checked", "");
        else container.removeAttribute("checked");
      }

      const after = await read();

      return { before, after };
    },
    { sampleId, settleMs }
  );
}

/**
 * WCAG 3.3.2 interaction probe. For every field in the captured form, reads what
 * the reader announces BEFORE any input, enters a value, then reads it again.
 * The question 3.3.2 asks is whether a label/instruction is *provided*; the
 * question a static transcript cannot answer is whether it is still provided
 * once the field is in use.
 *
 * The decisive comparison is NOT "did the phrase change" -- it always does, because
 * the entered value becomes part of the announcement. It is whether a segment
 * present in `before` (the name, the description) has gone MISSING from `after`:
 *
 *   placeholder-only : "textbox, placeholder Email address"
 *                   -> "textbox, Test entry"                      name LOST  => fail
 *   label + hint     : "textbox, Email address, <hint>"
 *                   -> "textbox, Email address, Test entry, <hint>" both kept => pass
 *
 * Two details the reader hands us for free: a name sourced from the placeholder
 * attribute is announced with a literal "placeholder " prefix, and native
 * `required` is announced as a "required" state.
 *
 * `html` is the field's WRAPPER (its parent, unless that is the form/body itself),
 * not the field alone -- the label and hint for a field live outside it, so a hint
 * that is removed on input is only visible at the wrapper level.
 *
 * Caller decides whether to invoke this: it is gated on `--sc 3.3.2` in
 * capture.mjs so 3.3.1 captures are untouched. Self-gates on the sample existing.
 *
 * @param {import('@playwright/test').Page} page
 * @param {string} sampleId
 * @param {{settleMs?: number}} opts
 * @returns {Promise<Array<{field: string, before: object, after: object}>|null>}
 */
export async function labelInstructionProbe(page, sampleId, { settleMs = 50 } = {}) {
  return page.evaluate(
    async ({ sampleId, settleMs }) => {
      const mod = window.__vsrMod;
      const container = document.querySelector(`[data-sample-id="${sampleId}"]`);
      if (!mod || !container) return null;

      const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

      // Scope the read to the FIELD itself. label[for=...] still resolves (the
      // accessible-name computation is document-wide), and scoping to the wrapper
      // instead would announce the <label> element rather than the input.
      const readPhrase = async (el) => {
        const v = new mod.Virtual();
        await v.start({ container: el });
        const phrase = (await v.lastSpokenPhrase()) || "";
        await v.stop();
        return phrase;
      };

      // The label/hint sit beside the field, so snapshot the wrapper -- but not
      // the whole form, which is already captured as element_html.
      const contextOf = (el) => {
        const parent = el.parentElement;
        if (!parent || parent === container || parent.tagName === "BODY") return el.outerHTML;
        return parent.outerHTML;
      };

      const read = async (el) => ({ phrase: await readPhrase(el), html: contextOf(el) });

      // A value that suits the field's type, so the page's own input/change
      // handlers behave the way they would for a real user.
      const valueFor = (el) => {
        switch ((el.getAttribute("type") || "").toLowerCase()) {
          case "email": return "someone@example.com";
          case "tel": return "07700900000";
          case "number":
          case "range": return "42";
          case "date": return "2026-01-01";
          case "password": return "Passw0rd!";
          case "url": return "https://example.com";
          default: return "Test entry";
        }
      };

      const fields = [
        ...container.querySelectorAll(
          "input:not([type='hidden']):not([type='submit']):not([type='button'])" +
            ":not([type='reset']):not([type='image']), select, textarea"
        ),
      ];

      const results = [];
      for (const [index, field] of fields.entries()) {
        const tag = field.tagName.toLowerCase();
        const type = (field.getAttribute("type") || "").toLowerCase();
        const before = await read(field);

        if (type === "checkbox" || type === "radio") {
          field.click();
          // Same IDL-vs-attribute mirror the 4.1.2 probe needs: click() flips the
          // `.checked` property but leaves the content attribute (and therefore
          // outerHTML, and the reader's state computation) untouched.
          if (field.checked) field.setAttribute("checked", "");
          else field.removeAttribute("checked");
        } else if (tag === "select") {
          const options = field.options || [];
          if (options.length > 1) {
            field.selectedIndex = field.selectedIndex === 0 ? 1 : 0;
            for (const opt of options) {
              if (opt.selected) opt.setAttribute("selected", "");
              else opt.removeAttribute("selected");
            }
          }
          field.dispatchEvent(new Event("input", { bubbles: true }));
          field.dispatchEvent(new Event("change", { bubbles: true }));
        } else {
          const value = valueFor(field);
          field.value = value;
          // Assigning .value updates the IDL property only -- it would never show
          // up in outerHTML, so `after.html` would look untouched. Mirror it, the
          // same way lib/interact.js does for the 3.3.1 pass.
          if (tag === "textarea") field.textContent = value;
          else field.setAttribute("value", value);
          field.dispatchEvent(new Event("input", { bubbles: true }));
          field.dispatchEvent(new Event("change", { bubbles: true }));
        }

        await sleep(settleMs);
        const after = await read(field);

        results.push({
          field: field.id || field.getAttribute("name") || `${tag}[${index}]`,
          before,
          after,
        });
      }

      return results;
    },
    { sampleId, settleMs }
  );
}

/**
 * Describe whatever currently has DOM focus, or null once focus has left the
 * document (`activeElement` falls back to `<body>`/`<html>`, which is how both
 * keyboard sweeps below detect the end of the tab cycle).
 *
 * Shared by the 2.4.3 focus-order sweep and the 2.1.2 keyboard-trap probe so the
 * two report a stop identically. `geometry` selects the 2.4.3 superset: position,
 * `obscured`, and the `aria-controls` subtree range, none of which 2.1.2 needs --
 * escapability is not a question about where a stop sits on screen.
 *
 * Key ORDER in the returned object is deliberate: it is what `JSON.stringify`
 * writes into the dataset column, so the geometry fields are spliced back into
 * exactly the positions the 2.4.3 capture already used.
 *
 * @param {import('@playwright/test').Page} page
 * @param {{geometry?: boolean}} opts
 * @returns {Promise<object|null>} the focused element's description, or null
 */
async function readActiveStop(page, { geometry = true } = {}) {
  return page.evaluate(async (geometry) => {
    const el = document.activeElement;
    // Focus left the document (browser chrome) -> end of the tab cycle.
    if (!el || el === document.body || el === document.documentElement) return null;

    const all = [...document.querySelectorAll("*")];
    let phrase = "";
    const mod = window.__vsrMod;
    if (mod) {
      const v = new mod.Virtual();
      await v.start({ container: el });
      phrase = (await v.lastSpokenPhrase()) || "";
      await v.stop();
    }

    const base = {
      phrase,
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute("role") || null,
      name: el.getAttribute("aria-label") || (el.textContent || "").trim().slice(0, 80) || null,
      id: el.id || null,
      tabindex: el.getAttribute("tabindex"),
    };
    if (!geometry) {
      // Position among all elements, so the sequence can be compared against
      // source order without needing the DOM itself.
      return { ...base, domIndex: all.indexOf(el) };
    }

    const rect = el.getBoundingClientRect();

    // Is something painted on top of this stop? Tabbing scrolls the focused
    // element into view, so its live viewport rect is valid here. An element
    // that is not the topmost thing at its own centre is sitting under an
    // overlay -- the modal case, where focus walks content the user cannot see
    // or click. Geometry alone cannot catch that: the obscured content is
    // often in a perfectly sensible position.
    let obscured = false;
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    if (
      rect.width > 0 && rect.height > 0 &&
      cx >= 0 && cy >= 0 && cx <= window.innerWidth && cy <= window.innerHeight
    ) {
      const topmost = document.elementFromPoint(cx, cy);
      obscured =
        !!topmost && topmost !== el && !el.contains(topmost) && !topmost.contains(el);
    }

    return {
      ...base,
      obscured,
      // Which element this stop claims to control, plus that element's subtree
      // as a domIndex range. querySelectorAll("*") is document order and a
      // subtree is contiguous within it, so [first, last] is exact -- which lets
      // the skill check mechanically whether focus actually moved INTO the
      // content this control just revealed, or off to somewhere unrelated.
      controls: el.getAttribute("aria-controls") || null,
      controlsRange: (() => {
        const id = el.getAttribute("aria-controls");
        if (!id) return null;
        const target = document.getElementById(id);
        if (!target) return null;
        const first = all.indexOf(target);
        if (first < 0) return null;
        return [first, first + target.querySelectorAll("*").length];
      })(),
      domIndex: all.indexOf(el),
      // Document-relative, so a mid-sweep scroll cannot distort the geometry.
      rect: {
        x: Math.round(rect.left + window.scrollX),
        y: Math.round(rect.top + window.scrollY),
        w: Math.round(rect.width),
        h: Math.round(rect.height),
      },
    };
  }, geometry);
}

/** Drop DOM focus so the next Tab lands on the page's first tabbable element. */
async function resetFocus(page) {
  await page.evaluate(() => {
    const el = document.activeElement;
    if (el && el !== document.body && typeof el.blur === "function") el.blur();
  });
}

/**
 * One Tab sweep of the page AS IT STANDS. Tabs from the top and records every
 * focus stop: what the reader announces there, where it sits on screen, and where
 * it sits in the DOM.
 *
 * Run twice by `focusOrderProbe` below -- once on the page as loaded, then again
 * after each in-page control is activated -- because "as it stands" is not one
 * state for a page with a lightbox or a disclosure in it.
 *
 * This is the ONE probe that cannot live inside `page.evaluate`. Native focus
 * traversal only happens for trusted key events, so `Virtual.press("Tab")` (which
 * dispatches a synthetic event at the reader's own cursor) does not move DOM focus
 * at all. Playwright's keyboard does. So this probe is a hybrid: Playwright drives
 * the Tab key, and a small `page.evaluate` reads each resulting stop.
 *
 * Whether an order "preserves meaning" is a judgement call no assertion can make,
 * so the probe does not judge -- it records what a person would look at:
 *
 *   tab order  : phone(tabindex 1) -> besttime(2) -> name(3)
 *   DOM order  : name(11) -> phone(14) -> besttime(17)
 *   visual (y) : name(102) -> phone(177) -> besttime(252)
 *
 * and leaves the comparison to the skill. Positions are stored DOCUMENT-relative
 * (`+ scrollY`), not viewport-relative: tabbing scrolls the page, so raw
 * getBoundingClientRect() values would encode scroll position instead of layout.
 *
 * Termination, as observed: after the last control the browser moves focus out of
 * the document and `activeElement` falls back to `<body>`, after which the cycle
 * restarts. So `<body>` is the end of the sweep. A stop that repeats the previous
 * element instead means focus is not advancing -- a keyboard trap, recorded as
 * `stalled` so the evidence can attribute it to 2.1.2 rather than to 2.4.3.
 *
 * @param {import('@playwright/test').Page} page
 * @param {number} maxStops
 * @returns {Promise<{stops: Array<object>, complete: boolean, truncated: boolean, stalled: boolean}>}
 */
async function tabSweep(page, maxStops) {
  // Start from a known state: nothing focused, so the first Tab lands on the
  // first tabbable element in the page's own order.
  await resetFocus(page);

  const stops = [];
  let complete = false;
  let stalled = false;

  for (let i = 0; i < maxStops; i++) {
    await page.keyboard.press("Tab");
    const stop = await readActiveStop(page, { geometry: true });

    if (!stop) {
      complete = true; // reached <body>: the cycle finished
      break;
    }

    const previous = stops[stops.length - 1];
    if (previous && previous.domIndex === stop.domIndex) {
      // Focus did not advance -- a trap. Record it once, then stop.
      stalled = true;
      stops.push({ stop: stops.length + 1, ...stop });
      break;
    }

    stops.push({ stop: stops.length + 1, ...stop });
  }

  return { stops, complete, truncated: stops.length >= maxStops && !complete, stalled };
}

/**
 * Which elements are focusable, before and after an activation.
 *
 * The difference between the two is the set of controls the interaction brought
 * into the tab sequence -- the only reliable way to detect a disclosure that
 * advertises itself with nothing. `aria-expanded`/`aria-controls` would be easier
 * to read, and a well-built widget has them; a lightbox wired up with a jQuery
 * click handler on a bare `<a href="#">` has neither, and that is exactly the
 * case the sweep was missing.
 *
 * `mode: "mark"` tags what is focusable now with an expando; `mode: "diff"`
 * returns what is focusable and was NOT tagged. Identity is carried on the
 * element object rather than by domIndex because a handler is free to MOVE the
 * content it reveals -- this suite's lightbox does exactly that
 * (`$('body').append($lbox)`), which renumbers every index after it and would
 * make a before/after comparison of index sets meaningless. An expando also
 * cannot leak into any captured HTML the way an attribute could.
 */
async function focusableSnapshot(page, mode) {
  return page.evaluate((mode) => {
    const SEL =
      'a[href], button, input, select, textarea, [tabindex], [contenteditable="true"]';
    const focusable = [...document.querySelectorAll(SEL)].filter((el) => {
      if (el.hasAttribute("disabled")) return false;
      if ((el.getAttribute("tabindex") || "0").trim() === "-1") return false;
      const style = getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") return false;
      return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
    });

    if (mode === "mark") {
      focusable.forEach((el) => {
        el.__focusableBefore = true;
      });
      return focusable.length;
    }

    const all = [...document.querySelectorAll("*")];
    return focusable
      .filter((el) => el.__focusableBefore !== true)
      .map((el) => ({
        domIndex: all.indexOf(el),
        tag: el.tagName.toLowerCase(),
        text: (el.textContent || "").trim().slice(0, 60),
      }));
  }, mode);
}

/**
 * Activate the page's in-page controls and record what each one does to the tab
 * sequence.
 *
 * The static sweep reads the page as it loads, and for a whole class of pages that
 * is the wrong state to read: a lightbox, a disclosure, a menu. Their content is
 * `hidden` until something is clicked, so the sweep truthfully reports one stop,
 * the skill truthfully answers "one stop is not a sequence", and a real defect is
 * returned as insufficient evidence. What 2.4.3 asks about those pages is
 * precisely what happens on activation -- does focus follow the content that just
 * appeared, or is the user left where they were with the new content somewhere
 * down the tab order.
 *
 * Only in-page controls are activated: `href="#"`, buttons, and things carrying a
 * button role or `aria-expanded`. Clicking `<a href="page.html">` would navigate
 * and the probe would be measuring a different document. `el.click()` is used
 * rather than Playwright's click so no actionability wait or real navigation is
 * involved -- the event is untrusted, which is irrelevant to a click handler
 * (unlike Tab, which needs a trusted event to move focus natively).
 *
 * The page is reloaded before each candidate so one trigger's effects cannot be
 * attributed to the next. Nothing is judged here: `focusMovedIntoRevealed` is a
 * set-membership test, and whether the resulting order preserves meaning is left
 * where every other 2.4.3 question is left.
 */
async function activationPass(page, { url, maxStops, maxTriggers = 5 }) {
  const IN_PAGE =
    'a[href="#"], a[href=""], a[href^="#"], button, [role="button"], [aria-expanded]';

  const candidates = await page.evaluate((sel) => {
    const all = [...document.querySelectorAll("*")];
    return [...document.querySelectorAll(sel)].map((el) => all.indexOf(el));
  }, IN_PAGE);

  const triggers = [];
  for (const domIndex of candidates.slice(0, maxTriggers)) {
    if (url) {
      await page.goto(url, { waitUntil: "load" });
      // The reload takes the injected reader with it, and every stop read after
      // this point would otherwise come back with an empty `phrase`.
      await injectVsr(page);
    }

    await focusableSnapshot(page, "mark");
    const trigger = await page.evaluate((index) => {
      const el = [...document.querySelectorAll("*")][index];
      if (!el) return null;
      // focus() before click() so this models a KEYBOARD activation. A user who
      // reached this control by Tab has focus on it at the moment it fires, and
      // "where is focus once the content opens" is the whole question here -- a
      // bare synthetic click() leaves activeElement on <body>, so the answer
      // would be an artefact of how the probe clicks rather than what the page
      // does.
      el.focus();
      el.click();
      return {
        tag: el.tagName.toLowerCase(),
        text: (el.textContent || "").trim().slice(0, 60),
        domIndex: index,
      };
    }, domIndex);
    if (!trigger) continue;

    const revealed = await focusableSnapshot(page, "diff");
    // Nothing came into the tab sequence, so this control is not a disclosure and
    // has nothing to say about focus order. Reporting it would put an entry on
    // every ordinary button on every page.
    if (!revealed.length) continue;

    const focusAfter = await readActiveStop(page, { geometry: true });
    // Asked of the element itself rather than by comparing domIndexes, for the
    // same reason the snapshot is: the revealed content may have been moved.
    const focusMovedIntoRevealed = await page.evaluate(() => {
      const el = document.activeElement;
      return !!el && el !== document.body && el.__focusableBefore !== true;
    });

    const sweep = await tabSweep(page, maxStops);
    triggers.push({
      trigger,
      revealed,
      focusAfter,
      focusMovedIntoRevealed,
      stopsAfter: sweep.stops,
      completeAfter: sweep.complete,
      stalledAfter: sweep.stalled,
    });
  }

  return triggers.length ? { triggers } : null;
}

export async function focusOrderProbe(page, { maxStops = 60, url = null } = {}) {
  const initial = await tabSweep(page, maxStops);
  // Reloaded inside, so this must be the last thing done to the page -- see the
  // step-4 note in capture.mjs.
  const activation = await activationPass(page, { url, maxStops });
  return { ...initial, activation };
}

/**
 * WCAG 2.4.6 headings-and-labels probe. Reproduces the "rotor" view: every
 * heading, form control, button and link on the page, with what the reader
 * ANNOUNCES for it, pulled out of document order.
 *
 * That framing is the point. Screen-reader users do not only read pages top to
 * bottom -- they pull up a headings menu or a form-controls list and read the
 * entries stripped of surrounding context. A heading that reads fine in flow can
 * be useless in that list: six sections all headed "Overview", or a field
 * labelled "Number" that only made sense because of a heading three inches above
 * it. The reading-order transcript hides this; the list exposes it.
 *
 * "Descriptive" also means descriptive OF something, so each heading carries the
 * content it introduces and each label/link the section it sits in. Without that,
 * only vagueness is judgeable -- never whether a heading is specific and WRONG,
 * e.g. "Payment details" introducing "Street address, Town or city, Postcode".
 *
 * `href` is recorded per link because it drives the one fully objective check
 * available here: the same link text pointing at DIFFERENT destinations is
 * ambiguous, while the same text pointing at the same destination (a "Contact us"
 * link in header, body and footer) is ordinary and must not be flagged.
 *
 * @param {import('@playwright/test').Page} page
 * @param {{sectionChars?: number}} opts
 * @returns {Promise<{headings: Array<object>, labels: Array<object>, links: Array<object>}|null>}
 */
export async function headingLabelProbe(page, { sectionChars = 200 } = {}) {
  return page.evaluate(
    async ({ sectionChars }) => {
      const mod = window.__vsrMod;
      if (!mod || !document.body) return null;

      const say = async (el) => {
        const v = new mod.Virtual();
        await v.start({ container: el });
        const phrase = (await v.lastSpokenPhrase()) || "";
        await v.stop();
        return phrase;
      };
      const clean = (s) => (s || "").replace(/\s+/g, " ").trim();

      const HEADING = "h1, h2, h3, h4, h5, h6, [role='heading']";
      const all = [...document.querySelectorAll("*")];
      const headingEls = [...document.querySelectorAll(HEADING)];

      const levelOf = (el) => {
        const aria = el.getAttribute("aria-level");
        if (aria) return parseInt(aria, 10) || null;
        const match = el.tagName.match(/^H([1-6])$/);
        return match ? parseInt(match[1], 10) : null;
      };

      // A heading's section runs to the next heading of the same or higher rank
      // (an equal or smaller level number). For an <h1> that is the whole page,
      // which is correct -- an h1 does introduce everything under it.
      const introducesOf = (el) => {
        const level = levelOf(el) || 6;
        const start = all.indexOf(el);
        let end = all.length;
        for (const other of headingEls) {
          const index = all.indexOf(other);
          if (index > start && (levelOf(other) || 6) <= level) {
            end = index;
            break;
          }
        }
        const parts = [];
        for (let i = start + 1; i < end; i++) {
          // Leaf elements only, so nesting does not repeat the same text.
          if (all[i].children.length === 0) parts.push(clean(all[i].textContent));
        }
        return clean(parts.join(" ")).slice(0, sectionChars);
      };

      // Nearest heading before this element, so a label or link carries the
      // section it belongs to -- the visual context a rotor list strips away.
      const headingAbove = (el) => {
        const index = all.indexOf(el);
        let found = null;
        for (const heading of headingEls) {
          if (all.indexOf(heading) < index) found = heading;
          else break;
        }
        return found ? clean(found.textContent) : null;
      };

      const headings = [];
      for (const el of headingEls) {
        headings.push({
          level: levelOf(el),
          phrase: await say(el),
          text: clean(el.textContent),
          introduces: introducesOf(el),
        });
      }

      // Controls, not <label> elements: a control may be named by aria-label with
      // no <label> at all, and it is the announced NAME that 2.4.6 judges.
      const labels = [];
      for (const el of document.querySelectorAll(
        "input:not([type='hidden']):not([type='submit']):not([type='button'])" +
          ":not([type='reset']):not([type='image']), select, textarea, button"
      )) {
        labels.push({
          phrase: await say(el),
          text: clean(el.textContent) || el.getAttribute("aria-label") || null,
          tag: el.tagName.toLowerCase(),
          type: el.getAttribute("type") || null,
          underHeading: headingAbove(el),
        });
      }

      const links = [];
      for (const el of document.querySelectorAll("a[href]")) {
        links.push({
          phrase: await say(el),
          text: clean(el.textContent),
          href: el.getAttribute("href"),
          underHeading: headingAbove(el),
        });
      }

      return { headings, labels, links };
    },
    { sectionChars }
  );
}

/**
 * WCAG 2.4.4 link-purpose probe. Every link on the page with what the reader
 * ANNOUNCES for it, where it goes, and — the part this criterion actually turns
 * on — its **programmatically determined link context**.
 *
 * That context is why this is a separate probe rather than a reading of the 2.4.6
 * rotor view. WCAG defines it as a CLOSED list: text in the same sentence,
 * paragraph, list item or table cell as the link, or in the header cell of a table
 * cell containing it, plus whatever is wired to the link by aria-describedby or
 * title. The rotor view records `underHeading` instead, and a nearest-preceding
 * heading is NOT on that list — a reader does not offer it alongside the link. So
 * the rotor can only ever see that four links say "Read more"; it cannot see the
 * sentence that makes each of them unambiguous, which is the whole of 2.4.4.
 *
 * The distinction that follows matters, and the skill leans on it: repeated link
 * text going to different destinations fails 2.4.4 only when the CONTEXT also
 * fails to tell them apart. Four "Read more" links each ending their own article's
 * paragraph pass this criterion (they fail 2.4.9 Link Only, which is AAA and out
 * of scope). Recording the context is what makes that judgeable instead of guessed.
 *
 * `sentence` is captured separately from `block` because they are separate items on
 * WCAG's list and they routinely disagree: a link at the end of a six-sentence
 * paragraph is disambiguated by the paragraph but not by its own sentence, and a
 * skill that only ever saw the paragraph would call that a pass without noticing it
 * had a weaker one.
 *
 * Read-only: no clicks, no focus changes, no navigation. Safe to run beside the
 * per-element transcripts.
 *
 * @param {import('@playwright/test').Page} page
 * @param {{contextChars?: number, maxLinks?: number}} opts
 * @returns {Promise<{links: Array<object>, truncated: boolean}|null>}
 */
export async function linkPurposeProbe(page, { contextChars = 320, maxLinks = 60 } = {}) {
  return page.evaluate(
    async ({ contextChars, maxLinks }) => {
      const mod = window.__vsrMod;
      if (!mod || !document.body) return null;

      const say = async (el) => {
        const v = new mod.Virtual();
        await v.start({ container: el });
        const phrase = (await v.lastSpokenPhrase()) || "";
        await v.stop();
        return phrase;
      };
      const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
      const cap = (s) => (s.length > contextChars ? s.slice(0, contextChars) + "..." : s);

      // The containers WCAG names as link context. <th>/<dt>/<figcaption>/
      // <blockquote> are not literally on the list, but they are the same
      // relationship -- the nearest block that a reader can be sent to as a unit.
      const BLOCK = "p, li, td, th, dd, dt, figcaption, blockquote";

      /** Text of the elements named by an id-list attribute (describedby/labelledby). */
      const textFromIds = (el, attr) =>
        (el.getAttribute(attr) || "")
          .split(/\s+/)
          .filter(Boolean)
          .map((id) => {
            const target = document.getElementById(id);
            return target ? clean(target.textContent) : "";
          })
          .filter(Boolean)
          .join(" ") || null;

      /**
       * The sentence containing the link, out of its block's text. Split on
       * terminal punctuation followed by space; if the link's text cannot be
       * located in any one sentence (it spans two, or the block is a fragment
       * with no punctuation at all) the whole block IS the sentence, which is
       * the honest answer rather than a guess.
       */
      const sentenceAround = (blockText, linkText) => {
        if (!blockText || !linkText) return null;
        const sentences = blockText.split(/(?<=[.!?])\s+/).filter(Boolean);
        const hit = sentences.find((s) => s.includes(linkText));
        return hit ? clean(hit) : null;
      };

      /**
       * Header cells for a link sitting in a table cell. `headers="…"` wins where
       * it is present; otherwise the <th>s of the cell's own row plus the nearest
       * <th> above it in the same column. Column indexing is positional, so a table
       * using colspan/rowspan may attribute the wrong column header -- recorded as
       * context, never as the deciding evidence.
       */
      const headersFor = (el) => {
        const cell = el.closest("td, th");
        if (!cell) return [];
        const explicit = (cell.getAttribute("headers") || "").split(/\s+/).filter(Boolean);
        if (explicit.length) {
          return explicit
            .map((id) => {
              const target = document.getElementById(id);
              return target ? clean(target.textContent) : "";
            })
            .filter(Boolean);
        }
        const table = cell.closest("table");
        const row = cell.parentElement;
        if (!table || !row) return [];
        const cells = [...row.children];
        const colIndex = cells.indexOf(cell);
        const found = [];
        for (const c of cells) {
          if (c !== cell && c.tagName === "TH") found.push(clean(c.textContent));
        }
        const rows = [...(table.rows || [])];
        const rowIndex = rows.indexOf(row);
        for (let r = rowIndex - 1; r >= 0; r--) {
          const candidate = rows[r].children[colIndex];
          if (candidate && candidate.tagName === "TH") {
            found.push(clean(candidate.textContent));
            break;
          }
        }
        return [...new Set(found.filter(Boolean))];
      };

      const linkEls = [...document.querySelectorAll("a[href], [role='link']")];
      const truncated = linkEls.length > maxLinks;

      const links = [];
      for (const el of linkEls.slice(0, maxLinks)) {
        const text = clean(el.textContent);
        const block = el.closest(BLOCK);
        // A link that is its own block (a bare <a> under <nav>, a card wrapper)
        // has no enclosing context to be disambiguated BY -- record null rather
        // than falling back to a parent that is really the whole page.
        const enclosing = block && block !== el ? clean(block.textContent) : null;
        // ...and a block whose ENTIRE text is the link adds nothing either.
        // `<p><a>Read more</a></p>` has an enclosing paragraph, but there is no
        // context inside it: recording "Read more" here would make a bare link
        // look as though it were disambiguated by itself.
        const blockText = enclosing && enclosing !== text ? enclosing : null;
        const images = [...el.querySelectorAll("img, svg, [role='img']")];

        links.push({
          phrase: await say(el),
          text,
          href: el.getAttribute("href"),
          // How the announced name is arrived at -- ARIA7/ARIA8 supply a name the
          // visible text does not, and that name is what the criterion is judged on.
          ariaLabel: el.getAttribute("aria-label") || null,
          labelledBy: textFromIds(el, "aria-labelledby"),
          title: el.getAttribute("title") || null,
          // Image-only links: the name comes from alt, and a missing alt is why
          // the reader falls back to announcing the URL.
          imgAlt: images.length ? images.map((i) => i.getAttribute("alt")) : null,
          context: {
            sentence: blockText ? cap(sentenceAround(blockText, text) || "") || null : null,
            block: blockText ? cap(blockText) : null,
            blockTag: blockText ? block.tagName.toLowerCase() : null,
            tableHeaders: headersFor(el),
            describedBy: textFromIds(el, "aria-describedby"),
          },
        });
      }

      return { links, truncated };
    },
    { contextChars, maxLinks }
  );
}

/**
 * WCAG 1.3.2 reading-order probe. Walks the reader's virtual cursor over the whole
 * page and records, for every step, what was announced AND where on the page it
 * came from.
 *
 * Not a duplicate of the 2.4.3 sweep. That one covers only FOCUSABLE components
 * and is driven by pressing Tab; this one covers ALL content, text included, and
 * is driven by the reader's own cursor. A page of CSS-reordered prose with no
 * focusable elements at all has a perfect tab order and an unreadable reading
 * order.
 *
 * The reading sequence is already captured -- `sr_transcript` is exactly that.
 * What it lacks is POSITION: a transcript reading "C, A, B" is indistinguishable
 * from a correct one without knowing where on the page each phrase came from.
 * Attaching position is this probe's entire job.
 *
 * Deliberately a SEPARATE walk from `traverse()`, which must stay untouched: it
 * produces `sr_transcript` on every row of every dataset, and changing it would
 * invalidate the regression baseline for every suite.
 *
 * Two things the spike established about the walk, both reflected here:
 *  - `activeNode` may be a TEXT node, so positioning resolves through
 *    `parentElement` first.
 *  - Each element yields TWO steps -- its role ("paragraph") then its text -- with
 *    the same domIndex. `isLeaf` is recorded so the consumer can restrict the
 *    order comparison to content-bearing leaves; including containers like <body>,
 *    whose rect spans everything, would distort the ranking.
 *
 * @param {import('@playwright/test').Page} page
 * @param {{maxSteps?: number}} opts
 * @returns {Promise<{steps: Array<object>, complete: boolean, truncated: boolean}>}
 */
export async function readingOrderProbe(page, { maxSteps = 120 } = {}) {
  return page.evaluate(
    async ({ maxSteps }) => {
      const mod = window.__vsrMod;
      if (!mod || !document.body) return null;

      const all = [...document.querySelectorAll("*")];
      const v = new mod.Virtual();
      await v.start({ container: document.body });

      const steps = [];
      const record = (phrase) => {
        const node = v.activeNode;
        const el = !node ? null : node.nodeType === 3 ? node.parentElement : node;
        const rect = el && el.getBoundingClientRect ? el.getBoundingClientRect() : null;
        steps.push({
          step: steps.length + 1,
          phrase: phrase || "",
          nodeType: node ? node.nodeType : null,
          tag: el ? el.tagName.toLowerCase() : null,
          isLeaf: el ? el.children.length === 0 : false,
          domIndex: el ? all.indexOf(el) : -1,
          // Document-relative, so a mid-walk scroll cannot distort the geometry.
          rect: rect
            ? {
                x: Math.round(rect.left + window.scrollX),
                y: Math.round(rect.top + window.scrollY),
                w: Math.round(rect.width),
                h: Math.round(rect.height),
              }
            : null,
        });
      };

      const first = await v.lastSpokenPhrase();
      if (first) record(first);

      let previous = first;
      let complete = false;
      for (let i = 0; i < maxSteps; i++) {
        await v.next();
        const phrase = await v.lastSpokenPhrase();
        // Same wrap detection traverse() uses: the reader cycles, so stop on the
        // true wrap (opening phrase returns after an "end of ..." boundary).
        if (steps.length && phrase === steps[0].phrase && /^end of\b/i.test(previous || "")) {
          complete = true;
          break;
        }
        record(phrase);
        previous = phrase;
      }
      await v.stop();

      return { steps, complete, truncated: !complete && steps.length >= maxSteps };
    },
    { maxSteps }
  );
}

/**
 * Read the region the trapped stops sit inside, so the "user is advised of the
 * method for moving focus away" half of 2.1.2 is judgeable.
 *
 * Returns a Playwright handle as well as the description, because phase 3 below
 * needs to ask whether this same element survived the Escape key -- and a domIndex
 * is worthless for that, since indexes shift the moment the DOM changes.
 *
 * The advisory text is the region's text minus the text of every INTERACTIVE
 * element in it: an instruction like "Press Escape to leave the calendar" lives
 * beside the controls, never inside them, and without that exclusion a grid's
 * advisory reads "11 12 13 14".
 *
 * Which ancestor counts as the region matters just as much. The nearest common
 * ancestor alone is too low -- for a single pinned grid cell it is the `role="row"`
 * one level up, and the instruction is attached to the `role="grid"` above that. So
 * the walk continues to the nearest enclosing WIDGET role, and only falls back to
 * the plain parent when there is none.
 *
 * @param {import('@playwright/test').Page} page
 * @param {number[]} indexes domIndexes of the trapped stops
 */
async function readTrapRegion(page, indexes) {
  const handle = await page.evaluateHandle((indexes) => {
    // Container roles a trap plausibly belongs to. The instruction for leaving a
    // composite widget is authored on the widget, not on the cell that has focus.
    const WIDGET =
      "[aria-modal], [role='dialog'], [role='alertdialog'], [role='grid'], " +
      "[role='treegrid'], [role='toolbar'], [role='listbox'], [role='menu'], " +
      "[role='menubar'], [role='tablist'], [role='tree'], [role='radiogroup'], " +
      "[role='combobox'], [role='application'], [role='group'], [role='region']";

    const all = [...document.querySelectorAll("*")];
    const els = indexes.map((i) => all[i]).filter(Boolean);
    if (!els.length) return null;

    // One trapped element: its wrapper, so text sitting BESIDE it is in scope.
    let region = els.length === 1 ? els[0].parentElement || els[0] : els[0];
    for (const el of els) {
      while (region && !region.contains(el)) region = region.parentElement;
    }
    if (!region) return null;
    return region.closest(WIDGET) || region;
  }, indexes);

  const element = handle.asElement();
  if (!element) {
    await handle.dispose();
    return { handle: null, region: null };
  }

  const region = await element.evaluate((region, indexes) => {
    const INTERACTIVE =
      "a[href], button, input, select, textarea, [tabindex], [contenteditable]";
    const all = [...document.querySelectorAll("*")];
    const els = indexes.map((i) => all[i]).filter(Boolean);

    // Text nodes in the region that belong to no control -- the prose around the
    // widget, which is where an instruction for leaving it would be written. Read
    // via a walker rather than by cloning-and-deleting so the live DOM is untouched.
    const walker = document.createTreeWalker(region, NodeFilter.SHOW_TEXT);
    const outside = [];
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const owner = node.parentElement ? node.parentElement.closest(INTERACTIVE) : null;
      // Skip only for a control INSIDE the region: `closest` would otherwise climb
      // past it and discard everything whenever the region has a focusable ancestor.
      if (owner && owner !== region && region.contains(owner)) continue;
      outside.push(node.nodeValue || "");
    }

    const unique = (values) => [...new Set(values.filter(Boolean))];
    return {
      tag: region.tagName.toLowerCase(),
      role: region.getAttribute("role") || null,
      ariaModal: region.getAttribute("aria-modal") || null,
      id: region.id || null,
      advisory: outside.join(" ").replace(/\s+/g, " ").trim().slice(0, 240) || null,
      // An explicitly declared shortcut is the strongest form of "advised of the
      // method" -- and the one this probe's key ladder cannot itself press.
      keyshortcuts: unique(
        [region, ...els].map((el) => el.getAttribute("aria-keyshortcuts"))
      ),
      // The region's own description as well as the controls', because an
      // instruction for leaving a composite widget is normally attached to the
      // widget -- and may point at text that sits outside it, where `advisory`
      // above would never see it.
      describedBy: unique(
        [region, ...els].flatMap((el) =>
          (el.getAttribute("aria-describedby") || "")
            .split(/\s+/)
            .filter(Boolean)
            .map((id) => (document.getElementById(id)?.textContent || "").trim())
        )
      ),
    };
  }, indexes);

  return { handle: element, region };
}

/**
 * WCAG 2.1.2 keyboard-trap probe. Answers one question: once the keyboard can
 * reach a component, can the keyboard get back out of it?
 *
 * A hybrid probe for the same reason the 2.4.3 sweep is one -- native focus moves
 * only for TRUSTED key events, so `Virtual.press` cannot drive it and Playwright's
 * keyboard has to. Escapability is not a question about layout, so this reads the
 * cheaper, geometry-free stop shape.
 *
 * The design turns on one fact about the criterion: **containing focus is not the
 * defect.** A conforming modal dialog is REQUIRED to cycle Tab within itself; it
 * conforms because Escape closes it. A probe that stopped at "focus is looping"
 * would therefore flag every well-built dialog on the web. So detecting the loop
 * is only phase 1, and the phases that try to GET OUT are what separate a trap
 * from a correctly contained dialog:
 *
 *   1. forward  -- Tab from the top until one of four things happens (see below)
 *   2. reverse  -- Shift+Tab, because a component you can back out of is escapable
 *   3. escape   -- the Escape key, then Tab, which is the documented way out of
 *                  every dialog pattern in APG
 *
 * `outcome` classifies phase 1:
 *
 *   escaped -- activeElement fell back to <body>: focus left the page unaided, so
 *              there is no trap and phases 2-3 are skipped
 *   stalled -- the same element twice in a row: focus is pinned, the signature of
 *              a keydown handler calling preventDefault() on Tab
 *   cycled  -- an already-visited element came back: focus is looping inside a
 *              subset of the page and never reaches the end
 *   cap     -- maxStops with no repeat and no exit. NOT a finding: a page with
 *              more tabbables than the cap looks identical. Reported as
 *              inconclusive so the skill abstains rather than guessing.
 *
 * Phases 2 and 3 run only for `stalled`/`cycled`. "Got out" means focus reached
 * <body> OR landed on an element outside the trapped set -- leaving the component
 * is what the SC asks for, not leaving the page.
 *
 * One thing the ladder deliberately does not do is guess at other keys. A widget
 * escapable only by `Ctrl+M` reads here as a trap, so `region.keyshortcuts` and
 * `region.advisory` are captured alongside: whether an advertised method excuses
 * the containment is a judgement, and it is handed over rather than assumed.
 *
 * NOTE: unlike every other page-level probe, this one MUTATES the page -- Escape
 * legitimately closes a dialog. It must therefore run AFTER the per-sample
 * transcripts in capture.mjs, never before.
 *
 * @param {import('@playwright/test').Page} page
 * @param {{maxStops?: number, settleMs?: number}} opts
 * @returns {Promise<{stops: Array<object>, outcome: string, cycle: object|null, region: object|null, reverse: object|null, escape: object|null}>}
 */
export async function keyboardTrapProbe(page, { maxStops = 40, settleMs = 80 } = {}) {
  await resetFocus(page);

  // ---- phase 1: forward sweep ----------------------------------------------
  const stops = [];
  const visited = new Map(); // domIndex -> the stop number that first saw it
  let outcome = "cap";
  let cycle = null;

  for (let i = 0; i < maxStops; i++) {
    await page.keyboard.press("Tab");
    const stop = await readActiveStop(page, { geometry: false });
    if (!stop) {
      outcome = "escaped";
      break;
    }

    const previous = stops[stops.length - 1];
    stops.push({ stop: stops.length + 1, ...stop });

    if (previous && previous.domIndex === stop.domIndex) {
      outcome = "stalled";
      break;
    }
    const firstSeen = visited.get(stop.domIndex);
    if (firstSeen !== undefined) {
      outcome = "cycled";
      // The loop body: everything from the first sighting up to the stop before
      // the repeat. The repeat itself is the proof, not a member.
      const members = stops.slice(firstSeen - 1, stops.length - 1).map((s) => s.domIndex);
      cycle = { startStop: firstSeen, length: members.length, members };
      break;
    }
    visited.set(stop.domIndex, stops.length);
  }

  if (outcome === "escaped" || outcome === "cap") {
    return { stops, outcome, cycle, region: null, reverse: null, escape: null };
  }

  // The set focus is stuck inside. For a stall that is the single pinned element.
  const trapped = cycle ? cycle.members : [stops[stops.length - 1].domIndex];
  const trappedSet = new Set(trapped);
  const { handle, region } = await readTrapRegion(page, trapped);

  // ---- phase 2: reverse sweep ----------------------------------------------
  // Focus is still sitting inside the trap, which is where Shift+Tab has to be
  // pressed from. A component you can back out of can be left with the keyboard.
  const reverse = { presses: 0, exited: false, exitedTo: null, path: [] };
  const backPresses = Math.max(3, (cycle ? cycle.length : 1) + 2);
  for (let i = 0; i < backPresses; i++) {
    await page.keyboard.press("Shift+Tab");
    reverse.presses += 1;
    const stop = await readActiveStop(page, { geometry: false });
    if (!stop) {
      reverse.exited = true; // reached <body>: out of the page entirely
      break;
    }
    reverse.path.push({ stop: reverse.path.length + 1, ...stop });
    if (!trappedSet.has(stop.domIndex)) {
      reverse.exited = true;
      reverse.exitedTo = stop;
      break;
    }
  }

  // ---- phase 3: Escape recovery --------------------------------------------
  // Only worth pressing when neither Tab direction got out. This is the phase a
  // conforming dialog passes on, and the only reason this probe can tell one
  // apart from a real trap.
  let escape = null;
  if (!reverse.exited) {
    await page.keyboard.press("Escape");
    await page.waitForTimeout(settleMs);
    const activeAfter = await readActiveStop(page, { geometry: false });
    // Did the region itself go away? Checked through the element handle, since
    // any domIndex taken before Escape is stale the moment the DOM changes.
    const regionHidden = handle
      ? await handle.evaluate(
          (el) =>
            !el.isConnected ||
            el.getClientRects().length === 0 ||
            el.getAttribute("aria-hidden") === "true"
        )
      : null;

    await page.keyboard.press("Tab");
    const afterTab = await readActiveStop(page, { geometry: false });
    escape = {
      activeAfter,
      afterTab,
      regionHidden,
      exited: afterTab === null || !trappedSet.has(afterTab.domIndex),
    };
  }

  if (handle) await handle.dispose();
  return { stops, outcome, cycle, region, reverse, escape };
}

/** The focusable components 3.2.1 is about: anything that can receive focus. */
const FOCUSABLE =
  "a[href], button, input:not([type='hidden']), select, textarea, " +
  "[tabindex]:not([tabindex='-1']), [contenteditable]";

/**
 * The components 3.2.2 is about: anything with a SETTING that can be changed.
 *
 * Buttons and links are deliberately absent, and their absence is the criterion, not an
 * oversight. Activating a button is a user REQUEST for whatever happens next, which
 * 3.2.2 explicitly permits ("changing the SETTING of a component") and 3.2.5 governs.
 * Only controls that hold a value belong here.
 */
const SETTABLE =
  "input:not([type='hidden']):not([type='submit']):not([type='button'])" +
  ":not([type='reset']):not([type='image']), select, textarea, " +
  "[role='checkbox'], [role='switch'], [role='radio'], [role='slider'], " +
  "[role='combobox'], [role='spinbutton'], [role='option'], [aria-pressed]";

/**
 * The visible elements matching `selector`, as Playwright ELEMENT HANDLES plus a
 * descriptor. Shared by the 3.2.1 and 3.2.2 probes.
 *
 * Handles, not `domIndex` values, and this is the one thing about these two probes that
 * cannot be done the way the others do it. Every other probe addresses elements by their
 * index into `document.querySelectorAll("*")`, which is safe because those probes do not
 * change the DOM. These two exist to provoke DOM changes: the moment a handler inserts a
 * hint, every index after it shifts by one and the probe starts driving the wrong
 * elements -- silently, and worst on precisely the pages whose handlers are benign. A
 * handle survives the mutation.
 *
 * `domIndex` is still recorded, for reporting and for comparison against the other
 * probes' output. It is just never used to find the element again.
 *
 * @param {import('@playwright/test').Page} page
 * @param {string} selector which components to collect (FOCUSABLE or SETTABLE)
 * @returns {Promise<Array<{handle: import('@playwright/test').ElementHandle, descriptor: object}>>}
 */
async function visibleHandles(page, selector) {
  const handles = await page.$$(selector);
  const entries = [];
  for (const handle of handles) {
    const descriptor = await handle.evaluate((el) => {
      if (el.getClientRects().length === 0) return null; // not rendered, cannot be focused
      const all = [...document.querySelectorAll("*")];
      return {
        domIndex: all.indexOf(el),
        tag: el.tagName.toLowerCase(),
        role: el.getAttribute("role") || null,
        id: el.id || null,
        // Whitespace collapsed: a <select>'s textContent is its options joined by
        // newlines, which would put line breaks through the rendered evidence table.
        name:
          el.getAttribute("aria-label") ||
          (el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 60) ||
          el.getAttribute("placeholder") ||
          null,
      };
    });
    if (descriptor) entries.push({ handle, descriptor });
    else await handle.dispose();
  }
  return entries;
}

/**
 * Arm the in-page recorders that the 3.2.1 and 3.2.2 probes read back, and clear
 * anything a previous component left behind. Installed fresh before each interaction,
 * so a component's record covers only what IT caused.
 *
 * Shared because nothing here is about focus. Both criteria ask the same question --
 * "did a change of context happen" -- and differ only in what triggers it: receiving
 * focus for 3.2.1, changing a setting for 3.2.2. The recorders are identical.
 *
 * `window.open` is OVERRIDDEN rather than watched for a real popup, and that is not
 * a shortcut -- it is the only thing that works here. Neither probe's interaction is
 * a real user gesture, so a genuine `window.open` would be blocked by the popup
 * blocker and the probe would observe nothing happening at all. Recording the ATTEMPT
 * survives that, and the attempt is what both criteria are about.
 *
 * `submit` is caught in the capture phase and prevented, for the same reason the
 * navigation path below is resumable: letting the form actually submit would tear
 * down the page and every component after this one would go unprobed.
 *
 * `HTMLFormElement.prototype.submit` is overridden as WELL as the event listener,
 * and both are needed. Calling `form.submit()` from script -- the usual way a page
 * auto-submits -- fires **no** `submit` event at all, by design in HTML: it skips
 * both validation and the event. Without the override, the commonest auto-submit
 * idiom in existence would be recorded only as a navigation, losing the fact that a
 * form was submitted, and would tear the page down on the way past. The listener
 * still earns its place: it catches a submit driven by activating a real control.
 *
 * @param {import('@playwright/test').Page} page
 */
async function armContextRecorders(page) {
  await page.evaluate(() => {
    const state = { opened: [], submitted: [], added: [], removed: 0, attributes: [] };
    window.__contextProbe = state;

    if (!window.__contextProbeInstalled) {
      window.__contextProbeInstalled = true;

      const nativeOpen = window.open;
      window.open = function (url) {
        const s = window.__contextProbe;
        if (s) s.opened.push(String(url == null ? "" : url));
        return null; // never actually open one; the call is the evidence
      };
      window.__nativeOpen = nativeOpen;

      const nameForm = (form) =>
        (form && (form.id || form.getAttribute("name") || form.getAttribute("action"))) ||
        "(unnamed form)";

      document.addEventListener(
        "submit",
        (event) => {
          const s = window.__contextProbe;
          if (s) s.submitted.push(nameForm(event.target));
          event.preventDefault();
        },
        true
      );

      // form.submit() fires no submit event, so the listener above cannot see it.
      for (const method of ["submit", "requestSubmit"]) {
        const native = HTMLFormElement.prototype[method];
        if (typeof native !== "function") continue;
        HTMLFormElement.prototype[method] = function () {
          const s = window.__contextProbe;
          if (s) s.submitted.push(nameForm(this));
          // Deliberately NOT calling through: submitting would unload the page and
          // every component after this one would go unprobed.
        };
      }

      const describe = (el) =>
        !el || !el.tagName
          ? null
          : {
              tag: el.tagName.toLowerCase(),
              role: el.getAttribute ? el.getAttribute("role") : null,
              id: el.id || null,
              ariaModal: el.getAttribute ? el.getAttribute("aria-modal") : null,
            };

      new MutationObserver((records) => {
        const s = window.__contextProbe;
        if (!s) return;
        for (const record of records) {
          if (record.type === "childList") {
            for (const node of record.addedNodes) {
              if (node.nodeType === 1) s.added.push(node.outerHTML.slice(0, 300));
              else if ((node.nodeValue || "").trim()) s.added.push(node.nodeValue.trim().slice(0, 300));
            }
            s.removed += record.removedNodes.length;
          } else if (record.type === "attributes") {
            // The TARGET's identity, not just the attribute name. A dialog already
            // in the DOM that merely becomes visible adds no node at all -- it is a
            // hidden/class/style change on a role="dialog" element, and without this
            // the single worst defect class would leave no trace.
            s.attributes.push({ ...describe(record.target), attribute: record.attributeName });
          }
        }
      }).observe(document.documentElement, {
        subtree: true,
        childList: true,
        attributes: true,
        characterData: false,
      });
    }
  });
}

/**
 * WCAG 3.2.1 on-focus probe. Focuses every component in turn, in isolation, and
 * records what changed as a result.
 *
 * The criterion: receiving focus must not initiate a CHANGE OF CONTEXT -- a change of
 * user agent, viewport, focus, or content that changes the meaning of the page.
 *
 * The design turns on a distinction that is the mirror image of 2.1.2's. There,
 * containing focus LOOKED like a defect and was correct. Here, changing content looks
 * like a defect and is **normal**: revealing a hint, showing a tooltip, expanding a
 * combobox's listbox in place are all ordinary, all correct, and all produce DOM
 * mutations. What fails is changing CONTEXT. So a probe reporting "the DOM changed on
 * focus" would flag every well-built form on the web, and the recorded signals are
 * deliberately split by how decidable they are:
 *
 *   unambiguous -- focus moved away, the page navigated, a window was opened, a form
 *                  was submitted. These are changes of context by definition.
 *   ambiguous   -- DOM mutations and nothing else. Rendered WITH the markup of what
 *                  appeared, because a revealed hint and an opened dialog differ only
 *                  in what the added node is, and handed to the model to weigh.
 *
 * Focus is applied PROGRAMMATICALLY, not by tabbing. Isolation is the reason: 3.2.1
 * asks what *this* component does when focused, and a Tab-driven sweep cannot separate
 * "component N stole focus" from "component N+1 was reached normally". `focus`/
 * `focusin` fire identically either way, which is what handlers listen for. The cost
 * is a known limit: a handler gated on `:focus-visible` or on `event.isTrusted` will
 * not fire for programmatic focus, so this probe cannot see it.
 *
 * Navigation is the one change that destroys the page. `location.href = ...` tears
 * down the execution context, so the read is wrapped and, when it throws, the
 * navigation is recorded and the fixture re-loaded before the next component. Cost is
 * one reload per navigating component, which is zero on a page that does not navigate.
 *
 * @param {import('@playwright/test').Page} page
 * @param {{url: string, settleMs?: number, maxComponents?: number}} opts
 * @returns {Promise<{components: Array<object>, focusedVia: string, truncated: boolean}|null>}
 */
export async function focusContextProbe(page, { url, settleMs = 120, maxComponents = 25 } = {}) {
  let entries = await visibleHandles(page, FOCUSABLE);
  if (!entries.length) return { components: [], focusedVia: "programmatic", truncated: false };

  // The fixture's own URL as the browser resolved it. Compared against rather than the
  // `url` argument, whose percent-encoding need not match byte for byte -- a spurious
  // mismatch there would mark EVERY component as having navigated.
  const baseUrl = page.url();
  const total = entries.length;
  const limit = Math.min(total, maxComponents);

  // Record where a navigation went as a PATH, not an absolute URL. The static server
  // binds an ephemeral port, so the absolute form would differ on every capture -- the
  // dataset would never diff clean against itself and the regression check would be
  // worthless. The path is the part that carries meaning anyway.
  const asPath = (absolute) => {
    try {
      const parsed = new URL(absolute);
      return decodeURIComponent(parsed.pathname) + parsed.search + parsed.hash;
    } catch {
      return absolute;
    }
  };

  const components = [];
  let navigated = false;

  const disposeAll = async () => {
    for (const entry of entries) await entry.handle.dispose();
  };

  for (let i = 0; i < limit; i++) {
    // A previous component navigated away. Restore the fixture so this one is probed
    // against the page it belongs to -- and re-acquire the handles, since the old ones
    // point into a document that no longer exists.
    if (navigated) {
      await disposeAll();
      await page.goto(url, { waitUntil: "load" });
      await injectVsr(page);
      entries = await visibleHandles(page, FOCUSABLE);
      navigated = false;
    }

    const entry = entries[i];
    if (!entry) break; // the reloaded page enumerated differently; nothing to probe

    const { handle, descriptor } = entry;
    await resetFocus(page);
    await armContextRecorders(page);

    const before = await page.evaluate(() => location.href);

    let record = null;
    try {
      await handle.evaluate((el) => {
        if (typeof el.focus === "function") el.focus();
      });
      await page.waitForTimeout(settleMs);

      const observed = await page.evaluate((before) => {
        const state = window.__contextProbe || {};
        return {
          opened: state.opened || [],
          submitted: state.submitted || [],
          mutations: {
            added: (state.added || []).length,
            removed: state.removed || 0,
            attributes: (state.attributes || []).length,
            addedNodes: (state.added || []).slice(0, 6),
            attributeTargets: (state.attributes || []).slice(0, 8),
          },
          urlChanged: location.href !== before,
        };
      }, before);

      // Asked of the handle, so a mutation that shifted this element's position cannot
      // turn "focus stayed put" into "focus moved".
      const focusHeld = await handle.evaluate((el) => el === document.activeElement);

      // Where focus ended up, when it did not stay. Same stop shape the 2.4.3 sweep and
      // the 2.1.2 ladder report, so a reader can compare them directly.
      const movedTo = focusHeld ? null : await readActiveStop(page, { geometry: false });

      record = { component: descriptor, focusHeld, ...observed, focusMovedTo: movedTo, navigatedTo: null };
    } catch (error) {
      // "Execution context was destroyed" -- the only thing that does that here is a
      // real navigation, which is itself the finding.
      navigated = true;
      record = {
        component: descriptor,
        focusHeld: false,
        opened: [],
        submitted: [],
        mutations: { added: 0, removed: 0, attributes: 0, addedNodes: [], attributeTargets: [] },
        urlChanged: true,
        focusMovedTo: null,
        navigatedTo: asPath(page.url()),
      };
    }

    // A navigation that COMPLETED before the read does not throw -- the evaluate runs
    // happily against the new document. So the URL is checked either way, and this is
    // what actually catches `location.href = ...` most of the time.
    if (page.url() !== baseUrl) {
      navigated = true;
      record.navigatedTo = asPath(page.url());
      record.focusHeld = false;
    }

    components.push(record);
  }

  await disposeAll();
  return { components, focusedVia: "programmatic", truncated: total > maxComponents };
}

/**
 * WCAG 3.2.2 on-input probe. Answers: does changing a component's SETTING
 * automatically cause a change of context, and if so, was the user warned first?
 *
 * The sibling of `focusContextProbe`, sharing its recorders and its per-component
 * record shape so `src/evidence.py` can render both with the same helpers. Three
 * things make it a distinct probe rather than a flag on that one.
 *
 * **1. The trigger is a setting change, not focus.** A jump menu that navigates on
 * `change` passes 3.2.1 and fails 3.2.2; the repo holds that exact page in both
 * suites, as a pass in one and a fail in the other.
 *
 * **2. Focus is applied BEFORE the recorders are armed.** This is the ordering the
 * probe turns on. A setting cannot be changed without focus touching the control
 * first, so with the recorders armed any earlier, every 3.2.1 on-focus defect would
 * be recorded a second time here as an on-input defect -- on the same fixtures, with
 * nothing in the data to say which criterion was actually at fault. Focusing first
 * and arming second puts whatever the focus handler did outside the measurement.
 *
 * **3. 3.2.2 has an exception and 3.2.1 has none.** Changing context on input is
 * permitted when "the user has been advised of the behavior before using the
 * component", so `advisory` is captured per component and the same behaviour can be
 * a pass or a fail depending on it. Same shape as 2.1.2's "advised of the method".
 *
 * Known limit, recorded in `changedVia`: the events are dispatched, not trusted, so a
 * handler gated on `event.isTrusted` never runs and the probe cannot see it.
 *
 * @param {import('@playwright/test').Page} page
 * @param {{url: string, settleMs?: number, maxComponents?: number}} opts
 * @returns {Promise<{components: Array<object>, changedVia: string, truncated: boolean}|null>}
 */
export async function inputContextProbe(page, { url, settleMs = 120, maxComponents = 25 } = {}) {
  let entries = await visibleHandles(page, SETTABLE);
  if (!entries.length) return { components: [], changedVia: "dispatched", truncated: false };

  const baseUrl = page.url();
  const total = entries.length;
  const limit = Math.min(total, maxComponents);

  // Paths, not absolute URLs: the static server binds an ephemeral port, so the
  // absolute form would differ on every capture and the dataset would never diff
  // clean against itself.
  const asPath = (absolute) => {
    try {
      const parsed = new URL(absolute);
      return decodeURIComponent(parsed.pathname) + parsed.search + parsed.hash;
    } catch {
      return absolute;
    }
  };

  const components = [];
  let navigated = false;

  const disposeAll = async () => {
    for (const entry of entries) await entry.handle.dispose();
  };

  for (let i = 0; i < limit; i++) {
    if (navigated) {
      await disposeAll();
      await page.goto(url, { waitUntil: "load" });
      await injectVsr(page);
      entries = await visibleHandles(page, SETTABLE);
      navigated = false;
    }

    const entry = entries[i];
    if (!entry) break;
    const { handle, descriptor } = entry;

    // What the page says about this control BEFORE it is touched. Read first, because
    // changing the setting may well remove or replace it.
    const advisory = await handle.evaluate((el) => {
      // A control's own NAME is not advice about its behaviour, so labels are
      // excluded from both fields below and reported separately. Folding them in
      // makes every control on every page look advised: the flag goes true for a bare
      // no-JS form, and the one comparison this criterion turns on -- the same select
      // with and without a warning -- stops separating them.
      const NOT_ADVICE =
        "a[href], button, input, select, textarea, [tabindex], [contenteditable], label";
      const clean = (text) => (text || "").replace(/\s+/g, " ").trim();

      const labelText = el.id
        ? clean(
            [...document.querySelectorAll("label")]
              .filter((l) => l.getAttribute("for") === el.id)
              .map((l) => l.textContent)
              .join(" ")
          )
        : "";

      // Programmatic association: the accessible description. The strong form of
      // "advised" -- unambiguously attached to the control and announced with it.
      const describedBy = [
        ...new Set(
          (el.getAttribute("aria-describedby") || "")
            .split(/\s+/)
            .filter(Boolean)
            .map((id) => clean(document.getElementById(id)?.textContent))
            .filter(Boolean)
        ),
      ];

      // Positional: text BEFORE the control in its group. 3.2.2 says "before using
      // the component", so a warning printed after it is not a warning -- the walk
      // stops at the control. Text inside other controls is skipped, or a <select>'s
      // own options would read back as advice, the trap the 2.1.2 region capture hit.
      const group = el.closest("div, fieldset, li, p, section") || el.parentElement;
      const preceding = [];
      if (group) {
        const walker = document.createTreeWalker(group, NodeFilter.SHOW_TEXT);
        while (walker.nextNode()) {
          const node = walker.currentNode;
          if (el.compareDocumentPosition(node) & Node.DOCUMENT_POSITION_FOLLOWING) break;
          const owner = node.parentElement ? node.parentElement.closest(NOT_ADVICE) : null;
          if (owner && group.contains(owner)) continue;
          const text = clean(node.nodeValue);
          if (text) preceding.push(text);
        }
      }
      const precedingText = preceding.join(" ").slice(0, 240) || null;

      return {
        label: labelText || null,
        describedBy,
        precedingText,
        // "There is text here that COULD be a warning", not "the user was advised".
        // Whether the wording actually warns of a change of context is a judgement
        // and stays with the model: a hint reading "We only use this to send you
        // updates" sets this true and advises nobody of anything.
        hasText: describedBy.length > 0 || !!precedingText,
      };
    });

    // Focus FIRST, settle, and only THEN start recording -- see the note above.
    let record = null;
    try {
      await handle.evaluate((el) => {
        if (typeof el.focus === "function") el.focus();
      });
      await page.waitForTimeout(settleMs);
    } catch {
      // Focusing it navigated: that is 3.2.1's finding, not this probe's. Record the
      // component as unmeasurable here rather than crediting the change to input.
      navigated = true;
      components.push({
        component: descriptor,
        advisory,
        settingChanged: false,
        focusHeld: false,
        opened: [],
        submitted: [],
        mutations: { added: 0, removed: 0, attributes: 0, addedNodes: [], attributeTargets: [] },
        urlChanged: false,
        focusMovedTo: null,
        navigatedTo: null,
        note: "focusing this component changed context before its setting could be changed (a 3.2.1 matter, not 3.2.2)",
      });
      continue;
    }

    if (page.url() !== baseUrl) {
      navigated = true;
      components.push({
        component: descriptor,
        advisory,
        settingChanged: false,
        focusHeld: false,
        opened: [],
        submitted: [],
        mutations: { added: 0, removed: 0, attributes: 0, addedNodes: [], attributeTargets: [] },
        urlChanged: false,
        focusMovedTo: null,
        navigatedTo: null,
        note: "focusing this component navigated the page before its setting could be changed (a 3.2.1 matter, not 3.2.2)",
      });
      continue;
    }

    // Where focus actually sits once the focus phase has settled -- NOT necessarily
    // this component. If focusing it moved focus (a 3.2.1 defect), focus is already
    // elsewhere, and comparing the after-state against the HANDLE would report that
    // as an on-input focus change. The baseline has to be whatever holds focus now,
    // so "focus moved" here can only mean "moved *because the setting changed*".
    const activeBefore = await page.evaluateHandle(() => document.activeElement);
    await armContextRecorders(page);
    const before = await page.evaluate(() => location.href);

    try {
      // Change the setting. The per-type handling mirrors `labelInstructionProbe`,
      // which already solves this for 3.3.2 -- deliberately duplicated rather than
      // shared, because that probe produces a committed regression baseline and the
      // README makes the same promise about `traverse()`.
      const settingChanged = await handle.evaluate((el) => {
        const tag = el.tagName.toLowerCase();
        const type = (el.getAttribute("type") || "").toLowerCase();
        const fire = () => {
          el.dispatchEvent(new Event("input", { bubbles: true }));
          el.dispatchEvent(new Event("change", { bubbles: true }));
        };

        if (type === "checkbox" || type === "radio") {
          // click() rather than setting .checked: assigning the property fires no
          // event at all, so the page's own handler would never run.
          el.click();
          return true;
        }
        if (tag === "select") {
          const options = el.options || [];
          if (options.length < 2) return false;
          el.selectedIndex = el.selectedIndex === 0 ? 1 : 0;
          fire();
          return true;
        }
        if (el.hasAttribute("aria-checked") || el.hasAttribute("aria-pressed") ||
            el.hasAttribute("aria-selected")) {
          el.click();
          return true;
        }
        const valueFor = () => {
          switch (type) {
            case "email": return "someone@example.com";
            case "tel": return "07700900000";
            case "number":
            case "range": return "42";
            case "date": return "2026-01-01";
            case "password": return "Passw0rd!";
            case "url": return "https://example.com";
            default: return "Test entry";
          }
        };
        if (typeof el.value === "undefined") return false;
        el.value = valueFor();
        fire();
        return true;
      });

      await page.waitForTimeout(settleMs);

      const observed = await page.evaluate((before) => {
        const state = window.__contextProbe || {};
        return {
          opened: state.opened || [],
          submitted: state.submitted || [],
          mutations: {
            added: (state.added || []).length,
            removed: state.removed || 0,
            attributes: (state.attributes || []).length,
            addedNodes: (state.added || []).slice(0, 6),
            attributeTargets: (state.attributes || []).slice(0, 8),
          },
          urlChanged: location.href !== before,
        };
      }, before);

      const focusHeld = await page.evaluate(
        (baseline) => document.activeElement === baseline,
        activeBefore
      );
      const movedTo = focusHeld ? null : await readActiveStop(page, { geometry: false });

      record = {
        component: descriptor,
        advisory,
        settingChanged,
        focusHeld,
        ...observed,
        focusMovedTo: movedTo,
        navigatedTo: null,
      };
    } catch (error) {
      navigated = true;
      record = {
        component: descriptor,
        advisory,
        settingChanged: true,
        focusHeld: false,
        opened: [],
        submitted: [],
        mutations: { added: 0, removed: 0, attributes: 0, addedNodes: [], attributeTargets: [] },
        urlChanged: true,
        focusMovedTo: null,
        navigatedTo: asPath(page.url()),
      };
    }

    await activeBefore.dispose();

    if (page.url() !== baseUrl) {
      navigated = true;
      record.navigatedTo = asPath(page.url());
      record.focusHeld = false;
    }

    components.push(record);
  }

  await disposeAll();
  return { components, changedVia: "dispatched", truncated: total > maxComponents };
}

/**
 * The six sensory characteristics 1.3.3 names, as a word lexicon.
 *
 * Crude on purpose, and the consumer is told so. "Right" also means correct, "below"
 * usually points at a section rather than a control, and "Green Party" is not a colour
 * reference. This finds CANDIDATE sentences; whether one is an instruction identifying
 * a component is a judgement the probe does not make and cannot make.
 */
const SENSORY_LEXICON = {
  position: [
    "on the right", "on the left", "to the right", "to the left", "right-hand",
    "left-hand", "above", "below", "at the top", "at the bottom", "top of the",
    "bottom of the", "beside", "next to", "adjacent", "opposite", "first column",
    "second column", "left column", "right column", "in the corner", "upper", "lower",
  ],
  colour: [
    "red", "green", "blue", "yellow", "orange", "purple", "pink", "grey", "gray",
    "black", "white", "coloured", "colored", "in colour", "in color", "highlighted in",
  ],
  shape: [
    "round", "circular", "circle", "square", "rectangular", "rectangle", "triangular",
    "triangle", "oval", "star-shaped", "arrow-shaped", "diamond", "shaped",
  ],
  size: [
    "large", "larger", "largest", "small", "smaller", "smallest", "big", "bigger",
    // "narrow" and "short" are deliberately absent: "narrow your search" and "short
    // delay" are ordinary prose, and they fired on two fixtures that mean neither.
    "tiny", "wide", "tall",
  ],
  orientation: [
    "portrait", "landscape", "horizontal", "vertical", "sideways", "upright",
    "top-left", "top-right", "bottom-left", "bottom-right",
  ],
  sound: [
    "beep", "chime", "tone sounds", "audio cue", "the sound", "a sound", "alarm",
    "when it rings", "audible",
  ],
};

/** Position and colour are the two categories a measurement can corroborate. */
const RESOLVABLE = ["position", "colour"];

/**
 * WCAG 1.3.3 sensory-characteristics probe. Finds candidate sensory references in the
 * page's prose and resolves them, where resolution is possible, against what is
 * actually rendered.
 *
 * This criterion is shaped unlike the others here. 2.1.2, 3.2.1 and 3.2.2 fail in
 * BEHAVIOUR; 2.4.3, 1.3.2 and 2.4.6 fail in STRUCTURE. 1.3.3 fails in PROSE: "click the
 * round button on the right" is a defect and "click the round Submit button on the
 * right" is not, and the markup is identical either way. So most of what the criterion
 * needs is already in `element_html` (the page-level sample carries the prose AND the
 * controls) and `parent_html` (the stylesheet). This probe deliberately does not restate
 * any of that. It supplies three things:
 *
 *  1. **Resolved layout geometry.** What is actually left/right/above/below is the
 *     product of flex, grid, float and absolute positioning. CSS rules are not
 *     positions; only the rendered box is one. No amount of reading the stylesheet
 *     yields this -- one fixture puts the "right-hand" links FIRST in source order
 *     precisely to prove the difference.
 *  2. **Computed colour.** `class="btn-primary"` says nothing until the cascade runs.
 *  3. **`namesInSentence`** -- for each sensory sentence, which controls' real
 *     accessible names appear inside that same sentence. A convenience rather than
 *     something underivable, but it is the decisive test: "press the green Submit
 *     button" names its referent, "press the green button" does not. The 1.3.3
 *     equivalent of 2.4.6's same-text-different-destination check.
 *
 * Four of the six characteristics -- shape, size, orientation, sound -- are detected but
 * NOT resolved: no measurement corroborates "round" or "after the beep". Each reference
 * says which of its categories carry corroboration, so a reader can tell measured
 * evidence from a bare lexicon hit.
 *
 * Read-only: no clicks, no key presses, no DOM mutation, so it runs beside the other
 * read-only page probes rather than in the post-transcript slot.
 *
 * @param {import('@playwright/test').Page} page
 * @param {{maxReferences?: number, maxControls?: number}} opts
 * @returns {Promise<{references: Array<object>, candidates: Array<object>, truncated: boolean}|null>}
 */
export async function sensoryReferenceProbe(page, { maxReferences = 40, maxControls = 60 } = {}) {
  return page.evaluate(
    async ({ lexicon, resolvable, maxReferences, maxControls }) => {
      const mod = window.__vsrMod;
      if (!mod || !document.body) return null;

      const say = async (el) => {
        const v = new mod.Virtual();
        await v.start({ container: el });
        const phrase = (await v.lastSpokenPhrase()) || "";
        await v.stop();
        return phrase;
      };
      const clean = (s) => (s || "").replace(/\s+/g, " ").trim();

      /**
       * Lexicon match on WORD boundaries, never as a substring. Plain `includes` had
       * "red" matching inside "required" and "considered", which invented a colour
       * reference on two pages that contain none -- and one of them is the fixture
       * that exists to prove ordinary prose is not a finding.
       * Multi-word and hyphenated entries are matched literally: they are specific
       * enough already, and  behaves awkwardly around punctuation.
       *
       * String.raw, not a plain string: "" in a JS string literal is the
       * BACKSPACE character, not a word boundary, so the naive spelling silently
       * matches nothing at all and every single-word entry in the lexicon stops
       * firing. Only the multi-word ones keep working, which makes it look like a
       * tuning problem rather than a broken regex.
       */
      const wordMatch = (haystack, word) =>
        /[\s-]/.test(word)
          ? haystack.indexOf(word) !== -1
          : new RegExp(String.raw`\b${word}\b`).test(haystack);

      // Document-relative, the convention 2.4.3 and 1.3.2 fixed: a viewport-relative
      // rect would encode scroll position and the capture would not be reproducible.
      const rectOf = (el) => {
        const r = el.getBoundingClientRect();
        return {
          x: Math.round(r.left + window.scrollX),
          y: Math.round(r.top + window.scrollY),
          w: Math.round(r.width),
          h: Math.round(r.height),
        };
      };

      /** Nearest named colour for an rgb() string, via hue. null when transparent. */
      const nameColour = (value) => {
        const m = /rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/.exec(value || "");
        if (!m) return null;
        const r = +m[1], g = +m[2], b = +m[3];
        const alpha = m[4] === undefined ? 1 : parseFloat(m[4]);
        if (alpha === 0) return null;
        const rn = r / 255, gn = g / 255, bn = b / 255;
        const max = Math.max(rn, gn, bn);
        const min = Math.min(rn, gn, bn);
        const light = (max + min) / 2;
        const delta = max - min;
        if (delta < 0.08) return light > 0.85 ? "white" : light < 0.15 ? "black" : "grey";
        let hue;
        if (max === rn) hue = ((gn - bn) / delta) % 6;
        else if (max === gn) hue = (bn - rn) / delta + 2;
        else hue = (rn - gn) / delta + 4;
        hue = Math.round(hue * 60);
        if (hue < 0) hue += 360;
        if (hue < 15 || hue >= 345) return "red";
        if (hue < 45) return "orange";
        if (hue < 70) return "yellow";
        if (hue < 165) return "green";
        if (hue < 255) return "blue";
        if (hue < 290) return "purple";
        return "pink";
      };

      // ---- the things an instruction could be pointing at ----------------------
      // Not only controls. Three kinds of referent, and all three are needed:
      //  - interactive elements, the usual target of "press the ... button";
      //  - <label>s, because in a form it is the label that carries the colour an
      //    instruction refers to ("fields in red are required");
      //  - named regions and headings, because "the Refine results panel on the right"
      //    points at a landmark, and without them the name in that sentence has
      //    nothing to match against and a conforming page reads as a failing one.
      const CANDIDATE =
        "a[href], button, input:not([type='hidden']), select, textarea, summary, " +
        "[role='button'], [role='link'], label, " +
        "nav, aside, [role='region'], [role='navigation'], [aria-label], " +
        "h1, h2, h3, h4, h5, h6";

      const candidates = [];
      for (const el of [...document.querySelectorAll(CANDIDATE)].slice(0, maxControls)) {
        if (el.getClientRects().length === 0) continue;
        const style = getComputedStyle(el);
        candidates.push({
          phrase: await say(el),
          name:
            el.getAttribute("aria-label") ||
            clean(el.textContent) ||
            el.getAttribute("title") ||
            el.getAttribute("placeholder") ||
            null,
          tag: el.tagName.toLowerCase(),
          role: el.getAttribute("role") || null,
          id: el.id || null,
          rect: rectOf(el),
          colour: {
            text: style.color,
            textName: nameColour(style.color),
            background: style.backgroundColor,
            backgroundName: nameColour(style.backgroundColor),
            borderRadius: style.borderTopLeftRadius,
            fontSize: style.fontSize,
          },
        });
      }

      // ---- candidate sensory sentences -----------------------------------------
      const BLOCK =
        "p, li, td, th, dd, dt, figcaption, blockquote, label, legend, " +
        "h1, h2, h3, h4, h5, h6, span, div";
      const pageMidX = document.documentElement.scrollWidth / 2;
      const pageHeight = document.documentElement.scrollHeight;

      const references = [];
      let truncated = false;

      for (const block of document.querySelectorAll(BLOCK)) {
        if (references.length >= maxReferences) {
          truncated = true;
          break;
        }
        // Leaf blocks only, so a wrapper does not repeat its children's prose.
        if (block.querySelector(BLOCK)) continue;
        if (block.getClientRects().length === 0) continue;
        const text = clean(block.textContent);
        if (!text) continue;

        for (const sentence of text.split(/(?<=[.!?])\s+/).filter(Boolean)) {
          const lower = sentence.toLowerCase();
          const categories = [];
          const matched = [];
          for (const category of Object.keys(lexicon)) {
            const hits = lexicon[category].filter((w) => wordMatch(lower, w));
            if (hits.length) {
              categories.push(category);
              for (const h of hits) matched.push(h);
            }
          }
          if (!categories.length) continue;

          // The decisive check: does a real control's accessible name appear in this
          // same sentence? Names under three characters are skipped -- a one-word
          // name like "Go" matches far too much ordinary prose to mean anything.
          const namesInSentence = [
            ...new Set(
              candidates
                .map((c) => c.name)
                .filter((n) => n && n.length >= 3 && lower.includes(n.toLowerCase()))
            ),
          ];

          const here = rectOf(block);
          const resolved = {};

          if (categories.indexOf("position") !== -1) {
            const centre = (c) => c.rect.x + c.rect.w / 2;
            const claims = {};
            if (lower.indexOf("right") !== -1) {
              claims.right = candidates.filter((c) => centre(c) > pageMidX).map((c) => c.name);
            }
            if (lower.indexOf("left") !== -1) {
              claims.left = candidates.filter((c) => centre(c) <= pageMidX).map((c) => c.name);
            }
            if (lower.indexOf("below") !== -1 || lower.indexOf("bottom") !== -1) {
              claims.below = candidates
                .filter((c) => c.rect.y > here.y + here.h)
                .map((c) => c.name);
            }
            if (lower.indexOf("above") !== -1 || lower.indexOf("top") !== -1) {
              claims.above = candidates
                .filter((c) => c.rect.y + c.rect.h < here.y)
                .map((c) => c.name);
            }
            resolved.position = {
              instructionAt: here,
              pageMidX: Math.round(pageMidX),
              pageHeight,
              claims,
            };
          }

          if (categories.indexOf("colour") !== -1) {
            const named = lexicon.colour.filter(
              (w) => wordMatch(lower, w) && w.length <= 7
            );
            resolved.colour = {
              named,
              matching: candidates
                .filter(
                  (c) =>
                    named.indexOf(c.colour.textName) !== -1 ||
                    named.indexOf(c.colour.backgroundName) !== -1
                )
                .map((c) => ({
                  name: c.name,
                  text: c.colour.text,
                  textName: c.colour.textName,
                  background: c.colour.background,
                  backgroundName: c.colour.backgroundName,
                })),
            };
          }

          references.push({
            sentence,
            element: {
              tag: block.tagName.toLowerCase(),
              role: block.getAttribute("role") || null,
              id: block.id || null,
            },
            rect: here,
            categories,
            matched: [...new Set(matched)],
            // Which of this reference's categories carry measured corroboration, so a
            // reader can tell resolved evidence from a bare lexicon hit.
            resolvedCategories: categories.filter((c) => resolvable.indexOf(c) !== -1),
            unresolvedCategories: categories.filter((c) => resolvable.indexOf(c) === -1),
            namesInSentence,
            resolved,
          });
          if (references.length >= maxReferences) {
            truncated = true;
            break;
          }
        }
      }

      return { references, candidates, truncated };
    },
    { lexicon: SENSORY_LEXICON, resolvable: RESOLVABLE, maxReferences, maxControls }
  );
}
