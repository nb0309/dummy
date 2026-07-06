// Tiny static file server for the capture run. Serving over http (rather than
// file://) gives the page a real origin, which is required for the Blob dynamic
// import() we use to load the virtual-screen-reader bundle in-page. Missing
// ../../assets/* still 404 harmlessly.

import http from "node:http";
import fs from "node:fs";
import path from "node:path";

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".htm": "text/html; charset=utf-8",
  ".css": "text/css",
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".svg": "image/svg+xml",
};

/**
 * @param {string} rootDir directory to serve
 * @returns {Promise<{url: string, close: () => Promise<void>}>}
 */
export function startServer(rootDir) {
  const root = path.resolve(rootDir);
  const server = http.createServer((req, res) => {
    try {
      const urlPath = decodeURIComponent((req.url || "/").split("?")[0]);
      const filePath = path.join(root, urlPath);
      if (!path.resolve(filePath).startsWith(root)) {
        res.statusCode = 403;
        return res.end("forbidden");
      }
      if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
        res.statusCode = 404;
        return res.end("not found");
      }
      res.setHeader("Content-Type", TYPES[path.extname(filePath).toLowerCase()] || "application/octet-stream");
      fs.createReadStream(filePath).pipe(res);
    } catch (e) {
      res.statusCode = 500;
      res.end(String(e));
    }
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      resolve({
        url: `http://127.0.0.1:${port}`,
        close: () => new Promise((r) => server.close(r)),
      });
    });
  });
}
