// Popup: "Remember this page" + settings (gateway URL / token).

const statusEl = document.getElementById("status");

function setStatus(msg) {
  statusEl.textContent = msg;
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

// Prefill settings.
(async () => {
  const cfg = await getConfig();
  document.getElementById("gatewayUrl").value = cfg.gatewayUrl;
  document.getElementById("token").value = cfg.token;
})();

document.getElementById("remember").addEventListener("click", async () => {
  const tab = await activeTab();
  if (!tab || !tab.url) return setStatus("No active tab.");
  setStatus("Remembering…");
  try {
    const res = await rememberUrl(tab.url, tab.title);
    setStatus(res.created ? `Remembered ✓ (${res.source_type})` : "Already saved.");
  } catch (e) {
    setStatus(`Error: ${e.message || e}`);
  }
});

document.getElementById("save").addEventListener("click", async () => {
  await setConfig({
    gatewayUrl: document.getElementById("gatewayUrl").value.trim() || "http://localhost:8080",
    token: document.getElementById("token").value.trim(),
  });
  setStatus("Settings saved.");
});
