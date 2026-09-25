/** Capture live screens with Chromium CDP; optional single-use Figma capture IDs.
 * node scripts/design/capture.mjs manifest.json output-directory [base-url]
 */
import { spawn } from "node:child_process";
import { once } from "node:events";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

const [manifestPath, output, base = "http://127.0.0.1:5174"] = process.argv.slice(2);
if (!manifestPath || !output) throw new Error("manifest and output directory required");
const manifest = JSON.parse(await fs.readFile(manifestPath, "utf8"));
const screens = Array.isArray(manifest) ? manifest : manifest.screens;
if (!screens?.every(screen => typeof screen.path === "string")) throw new Error("Each screen must specify a path");
await fs.mkdir(output, { recursive: true });
const profile = await fs.mkdtemp(path.join(os.tmpdir(), "ninna-capture-"));
const browser = spawn(process.env.CHROMIUM || "chromium", ["--headless", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--remote-debugging-port=0", `--user-data-dir=${profile}`, "about:blank"], { stdio: ["ignore", "ignore", "pipe"] });
const endpoint = await new Promise((resolve, reject) => {
  let log = "";
  const timer = setTimeout(() => reject(new Error("Chromium startup timed out")), 15000);
  browser.stderr.on("data", chunk => {
    log += chunk;
    const match = log.match(/DevTools listening on (ws:\/\/\S+)/);
    if (match) { clearTimeout(timer); resolve(match[1]); }
  });
  browser.once("error", reject);
});
const socket = new WebSocket(endpoint);
await once(socket, "open");
let ticket = 0;
const requests = new Map();
const submissions = new Map();
const captureRequests = new Set();
socket.addEventListener("message", event => {
  const result = JSON.parse(event.data);
  if (result.method === "Network.requestWillBeSent" && result.params.request.method === "POST" && /\/mcp\/capture\/.*\/submit/.test(result.params.request.url)) {
    captureRequests.add(result.params.requestId);
  }
  if (result.method === "Network.responseReceived" && captureRequests.has(result.params.requestId)) {
    submissions.set(result.sessionId, result.params.response.status);
  }
  const pending = requests.get(result.id);
  if (!pending) return;
  requests.delete(result.id); clearTimeout(pending.timer);
  result.error ? pending.reject(new Error(JSON.stringify(result.error))) : pending.resolve(result.result);
});
function send(method, params = {}, sessionId) {
  return new Promise((resolve, reject) => {
    const id = ++ticket;
    const timer = setTimeout(() => { requests.delete(id); reject(new Error(`${method} timed out`)); }, 60000);
    requests.set(id, { resolve, reject, timer });
    socket.send(JSON.stringify({ id, method, params, sessionId }));
  });
}
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const results = [];
try {
  // Limit simultaneous browsers to avoid slowing API reads and font loading.
  for (let start = 0; start < screens.length; start += 3) {
    await Promise.all(screens.slice(start, start + 3).map(async screen => {
      const { browserContextId } = await send("Target.createBrowserContext");
      try {
        const { targetId } = await send("Target.createTarget", { url: "about:blank", browserContextId });
        const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
        const call = (method, params) => send(method, params, sessionId);
        const evaluate = async expression => {
          const result = await call("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
          if (result.exceptionDetails) throw new Error(result.exceptionDetails.text + JSON.stringify(result.exceptionDetails.exception));
          return result.result.value;
        };
        await call("Page.enable");
        await call("Runtime.enable");
        await call("Network.enable");
        await call("Emulation.setDeviceMetricsOverride", { width: screen.width || 1440, height: screen.height || 900, deviceScaleFactor: 1, mobile: false });
        await call("Page.addScriptToEvaluateOnNewDocument", { source: `localStorage.setItem('ninna.sidebar.collapsed', ${JSON.stringify(String(!!screen.collapsed))});${screen.tab ? `sessionStorage.setItem(${JSON.stringify("ninna.view.run." + screen.path.split("/").at(-1) + ".tab")},${JSON.stringify(JSON.stringify(screen.tab))});` : ""}` });
        let url = base + screen.path;
        if (screen.captureId) {
          const endpoint = `https://mcp.figma.com/mcp/capture/${screen.captureId}/submit?bindVariables=true`;
          url += `#figmacapture=${screen.captureId}&figmaendpoint=${encodeURIComponent(endpoint)}&figmadelay=10000`;
        }
        await call("Page.navigate", { url });
        for (let attempt = 0; attempt < 60; attempt++) {
          await pause(250);
          if (await evaluate("!!document.querySelector('h1') && !document.querySelector('.loading')")) break;
          if (attempt === 59) throw new Error(`Screen did not load: ${screen.source}`);
        }
        await evaluate("document.fonts.ready.then(() => true)");
        await pause(1500);
        const metrics = await evaluate(`(() => {const typography=[];const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let node;while(node=walker.nextNode()){if(!node.textContent.trim()||/SCRIPT|STYLE/.test(node.parentElement.tagName))continue;const range=document.createRange();range.selectNodeContents(node);const rect=range.getBoundingClientRect();if(!rect.width||!rect.height)continue;const style=getComputedStyle(node.parentElement);typography.push({text:node.textContent.trim(),font:style.fontFamily,size:parseFloat(style.fontSize),weight:Number(style.fontWeight),x:rect.x,y:rect.y});}return {viewport:{width:innerWidth,height:innerHeight},documentHeight:document.documentElement.scrollHeight,overflow:document.documentElement.scrollWidth>innerWidth,typography,fonts:[...document.fonts].filter(f=>f.status==='loaded').map(f=>f.family),regions:[...document.querySelectorAll('.work-scroll,main,.page-header')].map(n=>({name:n.className,rect:n.getBoundingClientRect().toJSON(),scrollHeight:n.scrollHeight}))};})()`);
        const { data } = await call("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
        await fs.writeFile(path.join(output, `${screen.source}.png`), Buffer.from(data, "base64"));
        results.push({ ...screen, ...metrics });
        console.log(JSON.stringify({ source: screen.source, viewport: metrics.viewport, overflow: metrics.overflow }));
        if (screen.captureId) {
          for (let attempt = 0; attempt < 180 && !submissions.has(sessionId); attempt++) await pause(500);
          const status = submissions.get(sessionId);
          if (!status || status >= 400) throw new Error(`Figma submission failed for ${screen.source}: ${status || "timeout"}`);
          console.log(JSON.stringify({ source: screen.source, submitted: status }));
        }
      } finally {
        await send("Target.disposeBrowserContext", { browserContextId });
      }
    }));
  }
  await fs.writeFile(path.join(output, "index.json"), JSON.stringify(results, null, 2) + "\n");
} finally {
  socket.close(); browser.kill();
  await once(browser, "exit").catch(() => {});
  await fs.rm(profile, { recursive: true, force: true });
}
