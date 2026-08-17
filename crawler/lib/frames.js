// Inventory every nested browsing context (iframe/frame, and object/embed that
// created one) so capture cannot silently ignore payment widgets, chat, or
// embedded video. Same-origin frames are readable and can be sampled; anything
// we cannot enter is recorded as SKIPPED with a reason, never dropped.

import { extractSamples } from "./extract.js";

const PAGE_SC = new Set([
  "2.4.3",
  "2.4.4",
  "2.4.6",
  "1.3.2",
  "1.3.3",
  "2.1.2",
  "3.2.1",
  "3.2.2",
]);

/**
 * Wait for child frames that appear after load (chat widgets, payment iframes)
 * and for each to reach a load state. Bounded so a hanging frame cannot stall
 * the whole capture.
 *
 * @param {import('@playwright/test').Page} page
 * @param {{timeoutMs?: number}} [opts]
 */
export async function waitForChildFrames(page, { timeoutMs = 3000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  let last = page.frames().length;
  while (Date.now() < deadline) {
    await Promise.all(
      page.frames().map((frame) =>
        frame.waitForLoadState("domcontentloaded", { timeout: 400 }).catch(() => {})
      )
    );
    const now = page.frames().length;
    if (now === last) break;
    last = now;
    await page.waitForTimeout(120);
  }
}

async function hostAttrs(frame) {
  try {
    const el = await frame.frameElement();
    return el.evaluate((node) => ({
      tag: node.tagName.toLowerCase(),
      src: node.getAttribute("src") || node.getAttribute("data-src"),
      title: node.getAttribute("title") || node.getAttribute("aria-label"),
      name: node.getAttribute("name"),
      id: node.id || null,
      sandbox: node.getAttribute("sandbox"),
    }));
  } catch {
    return {
      tag: "iframe",
      src: null,
      title: null,
      name: frame.name() || null,
      id: null,
      sandbox: null,
    };
  }
}

async function describeFrame(frame, index) {
  const host = await hostAttrs(frame);
  const url = frame.url();
  let inner = null;
  let skipped = null;
  try {
    inner = await frame.evaluate(() => {
      const text = (document.body?.innerText || "").replace(/\s+/g, " ").trim();
      return {
        title: document.title || null,
        textPreview: text.slice(0, 160) || null,
        inputs: document.querySelectorAll("input, select, textarea, button").length,
        media: document.querySelectorAll("audio, video").length,
        headings: document.querySelectorAll("h1,h2,h3,h4,h5,h6").length,
        links: document.querySelectorAll("a[href]").length,
        forms: document.querySelectorAll("form").length,
      };
    });
  } catch {
    skipped = "cross-origin";
  }

  return {
    index,
    tag: host.tag,
    src: host.src,
    title: host.title,
    name: host.name,
    id: host.id,
    sandbox: host.sandbox,
    url,
    status: skipped ? "skipped" : "inspected",
    skipped,
    inner,
    sampled: 0,
  };
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {{sc?: string|null}} opts
 * @returns {Promise<{
 *   inventory: Array<object>,
 *   extraSamples: Array<object>,
 *   frameOf: Map<number, import('@playwright/test').Frame>,
 * }>}
 */
export async function collectFrames(page, { sc = null } = {}) {
  const children = page.frames().filter((frame) => frame !== page.mainFrame());
  const inventory = [];
  const extraSamples = [];
  const frameOf = new Map();

  for (let i = 0; i < children.length; i++) {
    const frame = children[i];
    frameOf.set(i, frame);
    const rec = await describeFrame(frame, i);
    inventory.push(rec);

    if (rec.status !== "inspected") continue;
    if (PAGE_SC.has(sc)) continue;

    const innerDoc = rec.inner;
    const barren =
      innerDoc &&
      !innerDoc.inputs &&
      !innerDoc.media &&
      !innerDoc.headings &&
      !innerDoc.links &&
      !innerDoc.forms &&
      !innerDoc.textPreview;
    if (barren) continue;

    try {
      const inner = await extractSamples(frame, { sc });
      rec.sampled = inner.length;
      for (const sample of inner) {
        extraSamples.push({ ...sample, frameIndex: i });
      }
    } catch {
      rec.status = "skipped";
      rec.skipped = "evaluate-failed";
    }
  }

  return { inventory, extraSamples, frameOf };
}
