// Smoke check: nested browsing contexts must be inventoried. Same-origin
// frames are sampled; cross-origin frames are listed SKIPPED — never dropped.
//
//   node test-frames.mjs

import { chromium } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { startServer } from "./lib/server.js";
import { gotoAndSettle } from "./lib/ready.js";
import { collectFrames } from "./lib/frames.js";
import { extractSamples } from "./lib/extract.js";

function assert(cond, message) {
  if (!cond) throw new Error(message);
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "guidepup-frames-"));
fs.writeFileSync(
  path.join(tmp, "chat.html"),
  `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Support</title></head>
<body>
  <h1>How can we help</h1>
  <form>
    <label for="q">Question</label>
    <input id="q" name="q" type="text">
    <button type="submit">Send</button>
  </form>
</body></html>`
);
fs.writeFileSync(
  path.join(tmp, "pay.html"),
  `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Payment</title></head>
<body><form><input name="card" aria-label="Card number"></form></body></html>`
);

const server = await startServer(tmp);
const foreignOrigin = server.url.replace("127.0.0.1", "localhost");
fs.writeFileSync(
  path.join(tmp, "host.html"),
  `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Checkout</title></head>
<body>
  <h1>Checkout</h1>
  <iframe title="Support" src="/chat.html"></iframe>
  <iframe title="Payment" src="${foreignOrigin}/pay.html"></iframe>
</body></html>`
);

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 800, height: 600 } });

try {
  await gotoAndSettle(page, `${server.url}/host.html`);

  const hostSamples = await extractSamples(page, { sc: null });
  const { inventory, extraSamples } = await collectFrames(page, { sc: null });

  assert(inventory.length === 2, `expected 2 frames, got ${inventory.length}`);

  const inspected = inventory.filter((f) => f.status === "inspected");
  const skipped = inventory.filter((f) => f.status === "skipped");
  assert(inspected.length === 1, `expected 1 inspected frame, got ${inspected.length}`);
  assert(skipped.length === 1, `expected 1 skipped frame, got ${skipped.length}`);
  assert(skipped[0].skipped === "cross-origin", `skip reason: ${skipped[0].skipped}`);
  assert(
    String(skipped[0].src || skipped[0].url).includes("pay.html"),
    "skipped frame should be the payment embed"
  );
  assert(inspected[0].sampled >= 1, "same-origin chat should yield inner samples");
  assert(extraSamples.length >= 1, "extraSamples should include the chat document");
  assert(
    extraSamples.every((s) => s.frameIndex === inspected[0].index),
    "inner samples must carry frameIndex"
  );

  const hostIframes = hostSamples.filter((s) =>
    String(s.elementHtmlRaw || "").toLowerCase().includes("<iframe")
  );
  assert(hostIframes.length >= 1, "host page should still sample the iframe element itself");

  console.log(
    `ok: ${inspected.length} inspected (sampled ${inspected[0].sampled}), ` +
      `${skipped.length} skipped (${skipped[0].skipped})`
  );
} finally {
  await browser.close();
  await server.close();
  fs.rmSync(tmp, { recursive: true, force: true });
}
