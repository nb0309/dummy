// Enumerate the "sample" elements on a page and capture each element's raw HTML
// + parent HTML, stamping a semantically-inert data-sample-id on each so the
// screen-reader transcript can be correlated back to it.
//
// Scalable across WCAG criteria: a declarative candidate sweep covers
//   - 1.1.1 non-text content  (img / svg / canvas / picture / input[type=image] / role=img)
//   - 1.2.1 time-based media  (audio / video / object / embed / iframe)
//   - 1.3.1 info & relationships (table / list / orphan list fragments)
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
 * @returns {Promise<Array>} one descriptor per sample element, in DOM order
 */
export async function extractSamples(page) {
  return page.evaluate(() => {
    // ---- selector vocabulary -------------------------------------------------
    const SEL = {
      image:
        "img, svg, canvas, picture, input[type='image'], [role='img'], [role='graphics-document']",
      media: "audio, video",
      embed: "object, embed, iframe",
      table: "table, [role='table'], [role='grid']",
      list: "ul, ol, dl, [role='list']",
      interactive: "a, button, [role='link'], [role='button']",
    };
    const MEDIAISH = [SEL.image, SEL.media, SEL.embed].join(", ");
    const CONTAINER = [SEL.table, SEL.list].join(", ");
    const CANDIDATES = [SEL.image, SEL.media, SEL.embed, SEL.table, SEL.list].join(", ");

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

    // Single document-order sweep over every candidate (querySelectorAll already
    // returns document order), applying escalation + container suppression.
    document.querySelectorAll(CANDIDATES).forEach((el) => {
      let target = el;
      let escalated = false;
      if (el.matches(MEDIAISH)) {
        const wrap = el.closest(SEL.interactive);
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

    // Re-sort to strict document order (multiple sweeps can interleave).
    targets.sort((a, b) => {
      if (a.el === b.el) return 0;
      const pos = a.el.compareDocumentPosition(b.el);
      return pos & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
    });

    // ---- capture raw HTML BEFORE injecting ids ------------------------------
    // Full element + parent HTML (kept uncapped so tables/lists are complete).
    const captured = targets.map(({ el, type }) => {
      const parent = el.parentElement;
      return {
        elementType: type,
        elementHtmlRaw: el.outerHTML,
        parentHtml: parent ? parent.outerHTML : null,
        _el: el,
      };
    });

    // ---- now inject ids -----------------------------------------------------
    return captured.map((c, i) => {
      const id = "sample-" + i;
      c._el.setAttribute("data-sample-id", id);
      delete c._el;
      return { sampleIndex: i, elementId: id, ...c };
    });
  });
}
