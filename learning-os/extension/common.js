// Shared helpers for the background worker and popup.
// Config (gateway URL + bearer token) lives in chrome.storage.local; set it from the popup.

const DEFAULTS = { gatewayUrl: "http://localhost:8080", token: "" };

async function getConfig() {
  const stored = await chrome.storage.local.get(DEFAULTS);
  return { ...DEFAULTS, ...stored };
}

async function setConfig(patch) {
  await chrome.storage.local.set(patch);
}

// Classify a URL into a Learning OS source_type. Non-YouTube defaults to "article".
function classify(url) {
  try {
    const u = new URL(url);
    const host = u.hostname.replace(/^www\./, "");
    if (host === "youtube.com" || host === "m.youtube.com" || host === "youtu.be") {
      return u.pathname.includes("/shorts/") ? "youtube_shorts" : "youtube";
    }
  } catch (_) {
    /* fall through */
  }
  return "article";
}

// POST the current URL to the gateway. Returns the parsed response body.
async function rememberUrl(url, title) {
  const { gatewayUrl, token } = await getConfig();
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const resp = await fetch(`${gatewayUrl}/v1/content`, {
    method: "POST",
    headers,
    body: JSON.stringify({ url, source_type: classify(url), title: title || null }),
  });
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(body.detail || `gateway ${resp.status}`);
  }
  return body;
}
