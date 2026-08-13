// Same-origin link discovery for the --url crawl mode. Kept separate from
// capture.mjs so the BFS loop there stays readable.

/**
 * Read every <a href> on the current page, resolved to absolute URLs by the
 * browser itself, and keep only same-origin http(s) links (no mailto:/tel:/
 * javascript:, no cross-origin). Hash fragments are stripped since they don't
 * denote a distinct document. Must be called before any probe that mutates or
 * navigates the page, so it sees the page as it was actually loaded.
 *
 * @param {import('@playwright/test').Page} page
 * @param {string} originFilter  the origin (protocol+host+port) to stay within
 * @returns {Promise<string[]>}
 */
export async function discoverLinks(page, originFilter) {
  const hrefs = await page.evaluate(() =>
    Array.from(document.querySelectorAll("a[href]")).map((a) => a.href)
  );
  const seen = new Set();
  const links = [];
  for (const href of hrefs) {
    if (!href.startsWith("http://") && !href.startsWith("https://")) continue;
    let parsed;
    try {
      parsed = new URL(href);
    } catch {
      continue;
    }
    if (parsed.origin !== originFilter) continue;
    parsed.hash = "";
    const clean = parsed.toString();
    if (seen.has(clean)) continue;
    seen.add(clean);
    links.push(clean);
  }
  return links;
}

/**
 * Derive a filesystem-safe identifier from a URL, used where fixtures use a
 * filename (sample_id/source_file). hostname + pathname, trailing slash
 * stripped, remaining separators collapsed to "_"; falls back to the
 * hostname alone for the root path.
 *
 * @param {string} absoluteUrl
 * @returns {string}
 */
export function urlToFile(absoluteUrl) {
  const parsed = new URL(absoluteUrl);
  const trimmedPath = parsed.pathname.replace(/\/+$/, "");
  const slug = `${parsed.hostname}${trimmedPath}`.replace(/[\\/]+/g, "_");
  return slug || parsed.hostname;
}
