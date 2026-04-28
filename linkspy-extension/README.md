# 🔗 LinkSpy — Chrome Extension

> **Real-time inline link checker — like Grammarly, but for links.**  
> Quiet, automatic, non-intrusive. Works on any page, zero backend, zero auth.

---

## ✨ Features

- **Automatic scanning** — checks every link the moment a page loads
- **Inline highlights** — colored underlines show link health at a glance
  - 🟢 Green = working (200-299)
  - 🟠 Orange = redirect (300-399)
  - 🔴 Red = broken (404, 410)
  - 🟣 Purple dashed = blocked/can't verify (401, 403, 429)
  - ⚪ Gray dotted = timeout
- **Status badges** — small inline badges next to broken/redirected links
- **Floating panel** — draggable summary widget with live stats
- **Dynamic detection** — MutationObserver catches links added after page load
- **SPA support** — detects route changes in React/Vue/etc
- **Popup controls** — toggle settings, trigger scans, jump to broken links

---

## 📦 Installation (Load Unpacked)

1. **Download/clone** this folder to your computer

2. Open Chrome and go to:
   ```
   chrome://extensions
   ```

3. Enable **Developer mode** (toggle in the top-right corner)

4. Click **"Load unpacked"**

5. Select the `linkspy-extension` folder

6. ✅ Done! The LinkSpy icon appears in your toolbar

> **Tip:** Pin the extension by clicking the puzzle-piece icon in Chrome's toolbar and pinning LinkSpy.

---

## 🏗 Architecture

```
┌──────────────────┐     sendMessage      ┌──────────────────┐
│   content.js     │ ──────────────────→  │  background.js   │
│                  │                      │  (service worker) │
│  • Collects <a>  │  ←──────────────────  │  • fetch() HEAD  │
│  • Highlights    │   partialResults /    │  • No CORS       │
│  • Panel UI      │   scanComplete        │  • Batching      │
│  • MutationObs   │                      │  • Caching       │
└──────────────────┘                      └──────────────────┘
         ↑
         │ chrome.tabs.sendMessage
         │
┌──────────────────┐
│   popup.js       │
│  • Settings UI   │
│  • Quick actions  │
└──────────────────┘
```

**Why background.js does the fetching:**  
Content scripts are subject to CORS. The background service worker is NOT — it can freely fetch any URL. This is the standard Manifest V3 pattern for cross-origin requests.

---

## ⚙ How It Works

1. **Page loads** → `content.js` collects all `<a href>` links
2. **Filters** out anchors (`#`), `mailto:`, `tel:`, `javascript:`, and non-HTTP URLs
3. **Deduplicates** — same URL referenced by multiple `<a>` tags gets checked once
4. **Sends URLs** to `background.js` in batches of 10
5. **Background worker** sends HEAD requests (falls back to GET if needed)
6. **Results stream back** incrementally — page updates progressively
7. **Highlights applied** — colored underlines + status badges on each link
8. **Panel updates** — floating widget shows live stats + progress bar
9. **MutationObserver** watches for dynamically added links (SPAs, infinite scroll)

---

## 📐 Performance

| Rule | Value |
|------|-------|
| Batch size | 10 URLs |
| Batch delay | 200ms |
| Request timeout | 8 seconds |
| Max links per page | 500 |
| Cache TTL | 5 minutes |
| MutationObserver debounce | 500ms |

---

## 🎨 Status Legend

| Status | Underline | Badge | Meaning |
|--------|-----------|-------|---------|
| OK | 🟢 Solid green | *none* | Link works fine |
| Broken | 🔴 Solid red | `404` | Page doesn't exist |
| Redirect | 🟠 Solid orange | `→` | Redirects somewhere |
| Blocked | 🟣 Dashed purple | `⊘` | Server blocked our check |
| Timeout | ⚪ Dotted gray | `⏱` | Didn't respond in time |
| Error | 🟡 Wavy yellow | `!` | Connection failed |

---

## ⚠ Known Limitations

1. **Soft 404s** — Some sites return HTTP 200 for non-existent pages. These will show as "working" since there's no reliable way to detect soft 404s without parsing page content.

2. **Authenticated pages** — Links requiring login will show as "blocked" (401/403). This is expected behavior.

3. **Rate limiting** — Some sites may rate-limit the checker, resulting in 429 responses shown as "blocked."

4. **Cross-origin iframes** — Links inside iframes from different domains cannot be checked.

5. **Very large pages** — Scanning is capped at 500 links per page to maintain performance.

6. **Service worker limitations** — Chrome may occasionally put the service worker to sleep during long scans.

---

## 📤 Packaging for Chrome Web Store

1. **Remove dev files:**
   ```
   del create-icons.js generate-icons.html panel.css.js
   ```

2. **Create ZIP:**
   ```
   # From the parent directory
   Compress-Archive -Path .\linkspy-extension\* -DestinationPath linkspy.zip
   ```

3. **Upload to Chrome Web Store:**
   - Go to [Chrome Developer Dashboard](https://chrome.google.com/webstore/devconsole)
   - Click "New Item" → upload `linkspy.zip`
   - Fill in listing details, screenshots, description
   - Submit for review

---

## 📁 File Structure

```
linkspy-extension/
├── manifest.json        ← Extension config (Manifest V3)
├── background.js        ← Service worker (HTTP fetching)
├── content.js           ← DOM injection + highlighting
├── content.css          ← Underline + badge styles
├── panel.js             ← Floating panel (Shadow DOM)
├── panel.css            ← Reference file (styles in panel.js)
├── popup.html           ← Toolbar popup UI
├── popup.js             ← Popup logic
├── popup.css            ← Popup styles
├── README.md            ← This file
└── icons/
    ├── icon16.png
    ├── icon48.png
    ├── icon128.png
    └── icon.svg         ← SVG source
```

---

## 📜 License

MIT — Free to use, modify, and distribute.
