// Enumerate the "sample" elements on a page and capture each element's raw HTML
// + parent HTML, stamping a semantically-inert data-sample-id on each so the
// screen-reader transcript can be correlated back to it.
//
// Scalable across WCAG criteria: a declarative candidate sweep covers
//   - 1.1.1 non-text content  (img / svg / canvas / picture / input[type=image] / role=img)
//   - 1.2.1 time-based media  (audio / video / object / embed / iframe)
//   - 1.3.1 info & relationships (table / list / orphan list fragments)
//   - 4.1.3 status messages   (role=status/alert/log/progressbar/…, aria-live, output/progress)
//   - 3.3.1 error identification / 3.3.2 labels & instructions (form) -- opt-in
//     via --sc 3.3.1 or --sc 3.3.2, see CANDIDATES
//   - 2.4.3 focus order / 2.4.4 link purpose / 2.4.6 headings & labels /
//     1.3.2 meaningful sequence / 2.1.2 no keyboard trap / 3.2.1 on focus /
//     3.2.2 on input (the page itself) -- opt-in via --sc, which takes an early
//     branch: page-level criteria, so one sample per file
// with a fallback content block so every file yields at least one sample.
// Media/image inside an interactive control escalate to that control (so the
// link/button is the sample), and structural containers suppress their
// descendants from becoming duplicate samples.
//
// We capture only three model inputs per sample: the element's raw outerHTML,
// its parent's outerHTML, and (later, in vsr.js) the screen-reader transcript.
// Raw HTML is captured BEFORE any id is injected, so the stored HTML never
// contains our marker (normalize.js strips it again as a belt-and-braces guard).
// `elementType` is retained internally only to drive sample selection; it is
// NOT emitted as a dataset column.

/**
 * @param {import('@playwright/test').Page} page
 * @param {{sc?: string|null}} opts criterion to opt into extra sweeps for
 * @returns {Promise<Array>} one descriptor per sample element, in DOM order
 */
export async function extractSamples(page, { sc = null } = {}) {
  return page.evaluate((sc) => {
    // ---- selector vocabulary -------------------------------------------------
    const SEL = {
      image:
        "img, svg, canvas, picture, input[type='image'], [role='img'], [role='graphics-document']",
      media: "audio, video",
      embed: "object, embed, iframe",
      table: "table, [role='table'], [role='grid']",
      list: "ul, ol, dl, [role='list']",
      interactive: "a, button, [role='link'], [role='button']",
      // 4.1.3 status messages: live-region hosts (explicit role/aria-live or a
      // native <output>/<progress>). A status message authored as a bare
      // <div>/<p> with no role matches nothing here on purpose -- it falls
      // through to the fallback content block, which is exactly the defect.
      status:
        "[role='status'], [role='alert'], [role='log'], [role='progressbar'], " +
        "[role='marquee'], [role='timer'], [aria-live], output, progress",
      // 4.1.2 name/role/value: custom widgets and native form controls whose
      // role/state/value must be programmatically exposed. Each selector here
      // requires an explicit role or input type, so -- like `status` above --
      // it cannot accidentally steal the fallback content block from an
      // ordinary page.
      control:
        "[role='checkbox'], [role='switch'], [role='radio'], [role='slider'], " +
        "[role='combobox'], [role='listbox'], [role='option'], [role='tab'], " +
        "[role='menuitemcheckbox'], [role='menuitemradio'], [role='spinbutton'], " +
        "input[type='checkbox'], input[type='radio'], input[type='range'], select, " +
        "[aria-pressed], [aria-expanded][aria-controls]",
      // 3.3.1 error identification / 3.3.2 labels & instructions. The form is the
      // sample because both SCs need the field, its label/hint and the error text
      // judged together -- a bare error <p> in isolation cannot show whether the
      // item in error is identified, and a bare <input> cannot show whether the
      // label sitting beside it is actually associated with it.
      form: "form, [role='form']",
    };
    const MEDIAISH = [SEL.image, SEL.media, SEL.embed].join(", ");
    const CONTAINER = [SEL.table, SEL.list].join(", ");
    // Elements a media/image icon should escalate to when nested inside one --
    // an icon-only <svg> inside a role="switch" wrapper is part of that
    // control, not a standalone 1.1.1 image sample.
    const INTERACTIVE_ESCALATION = [SEL.interactive, SEL.control].join(", ");
    // Opt-in per criterion: adding form to the default sweep would steal the
    // fallback block from every form page, and the absence of that block is what
    // carries the 4.1.3 defect signal. Both form-level criteria share the one
    // selector, so the gate is a membership test rather than a single ===.
    const FORM_SC = ["3.3.1", "3.3.2"];
    const CANDIDATES = [SEL.image, SEL.media, SEL.embed, SEL.table, SEL.list, SEL.status, SEL.control]
      .concat(FORM_SC.includes(sc) ? [SEL.form] : [])
      .join(", ");

    // ---- classify a resolved target element into an element_type -------------
    // Used only to drive selection/escalation; not emitted as a column.
    function classify(target, original, escalated) {
      const tag = target.tagName.toLowerCase();
      if (escalated) {
        // media/image lifted to its interactive wrapper
        const kind = original.matches(SEL.media) ? "media" : "image";
        const isButton =
          tag === "button" || (target.getAttribute("role") || "") === "button";
        return `${kind}-${isButton ? "button" : "link"}`;
      }
      if (target.matches(SEL.table)) return "table";
      if (tag === "ul" || tag === "ol" || tag === "dl") return tag;
      if (target.matches(SEL.list)) return "list";
      if (target.matches(SEL.status)) return "status";
      if (target.matches(SEL.control)) return "control";
      if (target.matches(SEL.form)) return "form";
      if (target.matches(SEL.image)) return "image";
      if (target.matches(SEL.media)) return "media";
      if (target.matches(SEL.embed)) return "embed";
      return tag;
    }

    // ---- select target elements, in document order --------------------------
    const targets = [];
    const seen = new Set();
    function add(el, type) {
      if (!el || seen.has(el)) return;
      seen.add(el);
      targets.push({ el, type });
    }

    // Sort to document order, snapshot raw HTML, then stamp correlation ids.
    // Shared by every sampling path so each one emits identical descriptors.
    function finish(selected) {
      // Re-sort to strict document order (multiple sweeps can interleave).
      selected.sort((a, b) => {
        if (a.el === b.el) return 0;
        const pos = a.el.compareDocumentPosition(b.el);
        return pos & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
      });

      // ---- capture raw HTML BEFORE injecting ids ----------------------------
      // Full element + parent HTML (kept uncapped so tables/lists are complete).
      const captured = selected.map(({ el, type }) => {
        const parent = el.parentElement;
        return {
          elementType: type,
          elementHtmlRaw: el.outerHTML,
          parentHtml: parent ? parent.outerHTML : null,
          _el: el,
        };
      });

      // ---- now inject ids ---------------------------------------------------
      return captured.map((c, i) => {
        const id = "sample-" + i;
        c._el.setAttribute("data-sample-id", id);
        delete c._el;
        return { sampleIndex: i, elementId: id, ...c };
      });
    }

    // 2.4.3 focus order is a PAGE-level criterion: the finding lives in the
    // sequence of focusable components across the whole page, not in any one
    // element. So under --sc 2.4.3 the page itself is the single sample and the
    // candidate sweep below is skipped entirely -- one row per file, which is
    // what the focus-order probe reports against.
    // Page-level criteria: the finding lives in a property of the whole page --
    // the focus SEQUENCE (2.4.3), the SET of headings and labels (2.4.6), the
    // READING sequence (1.3.2), whether focus can ESCAPE at all (2.1.2), what
    // happens when each component RECEIVES focus (3.2.1) or has its SETTING CHANGED
    // (3.2.2), or whether each link is distinguishable from the OTHER links (2.4.4)
    // -- not in any one element. These replace the candidate sweep rather than
    // adding to it, so each file yields one row.
    //
    // 2.4.4 belongs here and not in the element sweep even though a link IS a single
    // element, because "ambiguous" is a comparison: one "Read more" is only a defect
    // relative to the other three, and a per-link sample can never see them.
    const PAGE_SC = ["2.4.3", "2.4.4", "2.4.6", "1.3.2", "1.3.3", "2.1.2", "3.2.1", "3.2.2"];
    if (PAGE_SC.includes(sc)) {
      // <body>, deliberately NOT <main>: these criteria are judged on content that
      // routinely sits OUTSIDE main -- skip links, banner nav and footers carry
      // focus stops for 2.4.3 and headings/links for 2.4.6 -- so capturing main
      // would omit exactly the evidence they turn on. Taking body also makes
      // parent_html the <html> element, which carries the <head> stylesheet (the
      // CSS that reorders the page visually) and the <head> scripts (the keydown
      // handler that causes a 2.1.2 trap).
      if (document.body) add(document.body, "page");
      return finish(targets);
    }

    // Single document-order sweep over every candidate (querySelectorAll already
    // returns document order), applying escalation + container suppression.
    document.querySelectorAll(CANDIDATES).forEach((el) => {
      let target = el;
      let escalated = false;
      if (el.matches(MEDIAISH)) {
        const wrap = el.closest(INTERACTIVE_ESCALATION);
        if (wrap && wrap !== el) {
          target = wrap;
          escalated = true;
        }
      }
      if (seen.has(target)) return;
      add(target, classify(target, el, escalated));

      // Structural containers swallow their descendant media + row/cell/item
      // fragments so those don't surface as duplicate samples -- but NOT nested
      // tables/lists, which are legitimate separate samples (the whole point of
      // the "table-nested-within-table" / "improperly-nested-lists" defects).
      if (target.matches(CONTAINER)) {
        target
          .querySelectorAll(`${MEDIAISH}, tr, th, td, li, dt, dd, thead, tbody`)
          .forEach((c) => seen.add(c));
      }

      // A 3.3.1/3.3.2 form is judged whole, so it swallows everything inside it --
      // otherwise an error summary carrying role="alert" would also surface as a
      // second, evidence-poor row. Safe because querySelectorAll yields the
      // <form> before its own descendants, so the form is always added first.
      if (FORM_SC.includes(sc) && target.matches(SEL.form)) {
        target.querySelectorAll("*").forEach((c) => seen.add(c));
      }
    });

    // Orphans: list fragments outside their required parent (the 1.3.1 defect
    // that only exists because of the missing parent).
    document.querySelectorAll("li").forEach((li) => {
      if (!li.closest("ul, ol, menu") && !seen.has(li)) add(li, "orphan-li");
    });
    document.querySelectorAll("dt, dd").forEach((x) => {
      if (!x.closest("dl") && !seen.has(x)) add(x, "orphan-" + x.tagName.toLowerCase());
    });

    // Fallback: no structural/media target found (fake lists, layout-only
    // content, headings/forms/css/link cases) -> capture the main content block
    // so every file yields at least one sample.
    if (targets.length === 0) {
      const block = document.querySelector("main") || document.body;
      if (block) add(block, "block");
    }

    return finish(targets);
  }, sc);
}
