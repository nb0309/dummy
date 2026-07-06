// Enumerate the "sample" elements on a page and capture each element's raw HTML
// + parent context, stamping a semantically-inert data-sample-id on each so the
// screen-reader transcript and axe violations can be correlated back to it.
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
// Raw outerHTML / parentHTML are captured BEFORE any id is injected, so the
// stored HTML never contains our marker (normalize.js strips it again as a
// belt-and-braces guard).

/**
 * @param {import('@playwright/test').Page} page
 * @returns {Promise<Array>} one descriptor per sample element, in DOM order
 */
export async function extractSamples(page) {
  return page.evaluate(() => {
    const IMPLICIT_ROLE = {
      main: "main",
      nav: "navigation",
      header: "banner",
      footer: "contentinfo",
      aside: "complementary",
      section: "region",
      article: "article",
      table: "table",
      thead: "rowgroup",
      tbody: "rowgroup",
      tr: "row",
      th: "columnheader",
      td: "cell",
      ul: "list",
      ol: "list",
      dl: "list",
      li: "listitem",
      form: "form",
      h1: "heading",
      h2: "heading",
      h3: "heading",
      h4: "heading",
      h5: "heading",
      h6: "heading",
      a: "link",
      img: "img",
      audio: "audio",
      video: "video",
    };

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

    function cssPath(el) {
      if (!el || el.nodeType !== 1) return "";
      const parts = [];
      let node = el;
      while (node && node.nodeType === 1 && node.tagName.toLowerCase() !== "html") {
        const tag = node.tagName.toLowerCase();
        const parent = node.parentElement;
        if (!parent) {
          parts.unshift(tag);
          break;
        }
        const sameTag = Array.from(parent.children).filter(
          (c) => c.tagName === node.tagName
        );
        const idx = sameTag.indexOf(node) + 1;
        parts.unshift(sameTag.length > 1 ? `${tag}:nth-of-type(${idx})` : tag);
        node = parent;
      }
      return parts.join(" > ");
    }

    function tagPath(el) {
      const chain = [];
      let node = el.parentElement;
      while (node && node.nodeType === 1) {
        chain.unshift(node.tagName.toLowerCase());
        if (node.tagName.toLowerCase() === "body") break;
        node = node.parentElement;
      }
      return chain.join(" > ");
    }

    function ancestorRoles(el) {
      const roles = [];
      let node = el.parentElement;
      while (node && node.nodeType === 1) {
        const tag = node.tagName.toLowerCase();
        roles.unshift(node.getAttribute("role") || IMPLICIT_ROLE[tag] || tag);
        if (tag === "body") break;
        node = node.parentElement;
      }
      return roles;
    }

    function norm(text) {
      return (text || "").replace(/\s+/g, " ").trim();
    }

    // A short, human-readable selector for a node (tag + id / first class), used
    // to point the model at *which* descendant carries the CSS signal.
    function shortSel(node) {
      const tag = node.tagName.toLowerCase();
      if (node.id) return `${tag}#${node.id}`;
      const cls = (node.getAttribute("class") || "").trim().split(/\s+/)[0];
      return cls ? `${tag}.${cls}` : tag;
    }

    // Extract the computed CSS effects that are otherwise invisible to a DOM /
    // a11y-tree capture, walking the sample element and its descendants:
    //   - text INJECTED via ::before / ::after `content:` (absent from the DOM,
    //     so the screen reader never announces it) -> a 1.3.1 defect if it
    //     carries meaning (e.g. `#css-generated-text:after { content:'Pizza' }`).
    //   - text HIDDEN by computed `display:none` / `visibility:hidden` (removed
    //     from the a11y tree), covering class-based hiding, not just inline style.
    // Capped so a large container / fallback <body> can't produce an unbounded
    // dump; only the top of a hidden subtree is reported (parent-hidden skipped).
    function collectCssSignals(root) {
      const generated = [];
      const hidden = [];
      const CAP = 40;
      const nodes = [root, ...root.querySelectorAll("*")];
      for (const node of nodes) {
        if (node.nodeType !== 1) continue;
        for (const pseudo of ["::before", "::after"]) {
          let content;
          try {
            content = window.getComputedStyle(node, pseudo).content;
          } catch (e) {
            continue;
          }
          // Only a quoted string literal is injected text; skip none/normal,
          // and skip empty (`content:''`) which is decorative.
          const m = content && content.match(/^"((?:[^"\\]|\\.)*)"$/);
          if (!m) continue;
          const text = m[1].replace(/\\"/g, '"').trim();
          if (!text) continue;
          if (generated.length < CAP) {
            generated.push({ selector: shortSel(node), pseudo: pseudo.replace("::", ""), content: text });
          }
        }
        let cs;
        try {
          cs = window.getComputedStyle(node);
        } catch (e) {
          continue;
        }
        if (cs.display === "none" || cs.visibility === "hidden") {
          // Report only the top of a hidden subtree, not every nested node.
          const parent = node.parentElement;
          const pcs = parent && parent !== root.parentElement ? window.getComputedStyle(parent) : null;
          const parentHidden = pcs && (pcs.display === "none" || pcs.visibility === "hidden");
          const txt = norm(node.textContent);
          if (!parentHidden && txt && hidden.length < CAP) {
            hidden.push({
              selector: shortSel(node),
              method: cs.display === "none" ? "display:none" : "visibility:hidden",
              text: txt.slice(0, 300),
            });
          }
        }
      }
      return { generated, hidden };
    }

    // Raw <th>/<td> tag + scope per cell, row by row. This exists because the
    // computed accessibility tree (ax_subtree) reflects the BROWSER's best-effort
    // header-inference algorithm, which silently assigns a plausible-looking
    // columnheader/rowheader role to a <th> even when it has no `scope` --
    // masking exactly the kind of defect (e.g. a data value mistakenly marked up
    // as <th>, producing a confusing "double header" row) this skill needs to
    // catch. Reporting the raw tag+scope lets the model check the authored
    // markup directly instead of trusting the browser's forgiving guess.
    function collectTableCellStructure(rowNodes) {
      const MAX_ROWS = 20;
      const MAX_CELLS = 120;
      const out = [];
      let cellCount = 0;
      for (const r of rowNodes) {
        if (out.length >= MAX_ROWS || cellCount >= MAX_CELLS) break;
        const cells = r.querySelectorAll(":scope > td, :scope > th");
        const rowOut = [];
        for (const c of cells) {
          if (cellCount >= MAX_CELLS) break;
          rowOut.push({
            tag: c.tagName.toLowerCase(),
            scope: c.getAttribute("scope") || null,
            headers: c.getAttribute("headers") || null,
            id: c.getAttribute("id") || null,
            text: norm(c.textContent).slice(0, 60),
          });
          cellCount++;
        }
        if (rowOut.length) out.push(rowOut);
      }
      return out;
    }

    // ---- classify a resolved target element into an element_type -------------
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
    const captured = targets.map(({ el, type }) => {
      const parent = el.parentElement;
      const rows = el.matches("table, [role='table'], [role='grid']")
        ? el.querySelectorAll("tr, [role='row']")
        : null;
      let colCount = 0;
      if (rows) {
        rows.forEach((r) => {
          const n = r.querySelectorAll(":scope > td, :scope > th").length;
          if (n > colCount) colCount = n;
        });
      }
      const itemCount =
        type === "ul" || type === "ol"
          ? el.querySelectorAll(":scope > li").length
          : null;
      const cssSignals = collectCssSignals(el);
      const cellStructure = rows ? collectTableCellStructure(rows) : null;
      return {
        elementType: type,
        elementTag: el.tagName.toLowerCase(),
        elementSelector: cssPath(el),
        elementText: norm(el.textContent).slice(0, 2000),
        elementHtmlRaw: el.outerHTML,
        parentTag: parent ? parent.tagName.toLowerCase() : null,
        parentTagPath: tagPath(el),
        parentHtml: parent ? parent.outerHTML.slice(0, 6000) : null,
        ancestorRoles: ancestorRoles(el),
        rowCount: rows ? rows.length : null,
        colCount: rows ? colCount : null,
        itemCount,
        cssGeneratedContent: cssSignals.generated,
        hiddenContent: cssSignals.hidden,
        cellStructure,
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
