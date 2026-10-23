// SUIT Kiosk Extension - Background Service Worker
// Communicates with native host com.suit.kiosk via Chrome Native Messaging API
// and manages tab operations (opening board config, closing tab to return)

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (!request || !request.action) {
    sendResponse({ status: "error", error: "No action specified" });
    return false;
  }

  // 1. Handle Tab Operations
  if (request.action === "close_tab") {
    if (sender && sender.tab && sender.tab.id) {
      chrome.tabs.remove(sender.tab.id, () => {
        sendResponse({ status: "ok" });
      });
    } else {
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (tabs && tabs[0] && tabs[0].id) {
          chrome.tabs.remove(tabs[0].id, () => sendResponse({ status: "ok" }));
        } else {
          sendResponse({ status: "error", error: "No active tab found" });
        }
      });
    }
    return true;
  }

  if (request.action === "open_tab") {
    const targetUrl = request.url || "http://localhost:3180/config";
    chrome.tabs.create({ url: targetUrl }, (tab) => {
      sendResponse({ status: "ok", tabId: tab ? tab.id : null });
    });
    return true;
  }

  if (request.action === "open_board_config") {
    findBoardConfigUrl().then((url) => {
      chrome.tabs.create({ url }, (tab) => {
        sendResponse({ status: "ok", url, tabId: tab ? tab.id : null });
      });
    });
    return true;
  }

  // 2. System operations. Ubuntu/Chromium Snap: localhost bridge (native
  // messaging is sandboxed there). Fedora: native messaging as before.
  getBridgeConfig().then((bridge) => {
    if (bridge) {
      callBridge(bridge, request).then(sendResponse);
    } else {
      callNativeHost(request, sendResponse);
    }
  });
  return true; // Required to keep sendResponse valid asynchronously
});

// bridge_config.json is written by SUIT next to the extension files only in
// bridge mode. It is not web-accessible, so pages cannot read the token.
let bridgeConfigPromise = null;
function getBridgeConfig() {
  if (!bridgeConfigPromise) {
    bridgeConfigPromise = fetch(chrome.runtime.getURL("bridge_config.json"))
      .then((r) => (r.ok ? r.json() : null))
      .then((cfg) => (cfg && cfg.url && cfg.token ? cfg : null))
      .catch(() => null);
  }
  return bridgeConfigPromise;
}

async function callBridge(bridge, request) {
  try {
    const resp = await fetch(bridge.url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-SUIT-Token": bridge.token },
      body: JSON.stringify({ action: request.action }),
    });
    const data = await resp.json().catch(() => null);
    return data || { status: "error", error: `Bridge HTTP ${resp.status}` };
  } catch (err) {
    return { status: "error", error: "SUIT kiosk bridge not running" };
  }
}

function callNativeHost(request, sendResponse) {
  try {
    chrome.runtime.sendNativeMessage(
      "com.suit.kiosk",
      request,
      (response) => {
        if (chrome.runtime.lastError) {
          console.error("SUIT Kiosk Native Message error:", chrome.runtime.lastError.message);
          sendResponse({
            status: "error",
            error: chrome.runtime.lastError.message
          });
        } else {
          sendResponse(response || { status: "ok" });
        }
      }
    );
  } catch (err) {
    console.error("Failed sending native message:", err);
    sendResponse({ status: "error", error: String(err) });
  }
}

// Autodarts board manager: 3180 by default, 3182 on some installs. Probed
// from the service worker (covered by host_permissions), not from the page.
async function findBoardConfigUrl() {
  for (const port of [3180, 3182]) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 1500);
    try {
      await fetch(`http://127.0.0.1:${port}/api/state`, { cache: "no-store", signal: controller.signal });
      return `http://localhost:${port}/config`;
    } catch (err) {
      // closed port or timeout: try the next one
    } finally {
      clearTimeout(timer);
    }
  }
  return "http://localhost:3180/config";
}
