// Smoke check: content that only mounts when scrolled into view is missed if
// capture treats `load` as "the page is ready". settlePage must reveal it and
// then return to the top.
//
//   node test-ready.mjs

import { chromium } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import url from "node:url";

import { startServer } from "./lib/server.js";
import { settlePage } from "./lib/ready.js";

const HERE = path.dirname(url.fileURLToPath(import.meta.url));

const PAGES = {
  "lazy-scroll.html": `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>lazy</title></head>
<body>
  <p id="above">above the fold</p>
  <div style="height:2500px"></div>
  <p id="sentinel">sentinel</p>
  <script>
    const sentinel = document.getElementById("sentinel");
    new IntersectionObserver((entries) => {
      if (!entries[0] || !entries[0].isIntersecting) return;
      if (document.getElementById("lazy-loaded")) return;
      const el = document.createElement("p");
      el.id = "lazy-loaded";
      el.textContent = "loaded on scroll";
      document.body.appendChild(el);
    }).observe(sentinel);
  </script>
</body></html>`,
};

function assert(cond, message) {
  if (!cond) throw new Error(message);
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "guidepup-ready-"));
for (const [name, html] of Object.entries(PAGES)) {
  fs.writeFileSync(path.join(tmp, name), html);
}

const server = await startServer(tmp);
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 800, height: 600 } });

try {
  await page.goto(`${server.url}/lazy-scroll.html`, { waitUntil: "load" });
  const before = await page.evaluate(() => !!document.getElementById("lazy-loaded"));
  assert(!before, "lazy node must not exist at load — sentinel is below the fold");

  await settlePage(page, { pauseMs: 50, networkIdleMs: 200 });

  const after = await page.evaluate(() => !!document.getElementById("lazy-loaded"));
  assert(after, "settlePage should scroll far enough to mount the lazy node");

  const y = await page.evaluate(() => window.scrollY);
  assert(y === 0, `settlePage must return to the top, scrollY was ${y}`);

  console.log("ok: scroll-triggered content is revealed, then viewport restored");
} finally {
  await browser.close();
  await server.close();
  fs.rmSync(tmp, { recursive: true, force: true });
}
