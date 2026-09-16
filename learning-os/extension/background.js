// Service worker: right-click "Remember this" context menu + notifications.
// (The toolbar button opens popup.html, which has its own "Remember this page" button.)
importScripts("common.js");

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "remember-this",
    title: "Remember this",
    contexts: ["page", "link", "selection", "video"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== "remember-this") return;
  const url = info.linkUrl || info.pageUrl || (tab && tab.url);
  if (!url) return;
  try {
    const res = await rememberUrl(url, tab && tab.title);
    notify(res.created ? "Remembered ✓" : "Already saved", url);
  } catch (e) {
    notify("Couldn't remember", String(e.message || e));
  }
});

function notify(title, message) {
  chrome.notifications.create({
    type: "basic",
    iconUrl: "icon128.png",
    title,
    message: message.slice(0, 200),
  });
}
