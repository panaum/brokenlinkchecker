/**
 * LinkSpy — Content Script
 * Runs on every page. Collects links, sends to background for checking,
 * highlights results inline, manages MutationObserver for dynamic content.
 */

;(function () {
  'use strict';

  /* ───────── Constants ───────── */
  const MAX_LINKS = 500;
  const SKIP_PROTOCOLS = ['data:', 'blob:', 'chrome:', 'chrome-extension:', 'about:', 'file:', 'moz-extension:'];
  const SKIP_PREFIXES = ['#', 'mailto:', 'tel:', 'javascript:'];
  const STATUS_CLASSES = ['linkspy-ok', 'linkspy-broken', 'linkspy-redirect', 'linkspy-blocked', 'linkspy-timeout', 'linkspy-error', 'linkspy-scanning'];

  /* ───────── State ───────── */
  let urlMap = new Map();        // url → Set of <a> elements
  let results = {};              // url → { status, code }
  let panel = null;              // LinkSpyPanel instance
  let settings = {
    autoScan: true,
    showBadges: true,
    highlightOk: false,
  };
  let isScanning = false;
  let totalLinks = 0;
  let mutationTimer = null;
  let spaTimer = null;

  /* ───────── Settings ───────── */
  async function loadSettings() {
    try {
      const data = await chrome.storage.local.get(['autoScan', 'showBadges', 'highlightOk']);
      if (data.autoScan !== undefined) settings.autoScan = data.autoScan;
      if (data.showBadges !== undefined) settings.showBadges = data.showBadges;
      if (data.highlightOk !== undefined) settings.highlightOk = data.highlightOk;
    } catch (e) {}
  }

  /* ───────── Link Collection ───────── */
  function collectLinks() {
    urlMap.clear();
    const anchors = document.querySelectorAll('a[href]');
    const seen = new Set();

    for (const a of anchors) {
      const href = (a.getAttribute('href') || '').trim();

      // Skip empty, anchors, mailto, tel, javascript
      if (!href || SKIP_PREFIXES.some(p => href.startsWith(p))) continue;

      // Resolve to absolute URL
      let absolute;
      try {
        absolute = new URL(href, window.location.href).href;
      } catch (e) {
        continue;
      }

      // Skip non-http protocols
      if (SKIP_PROTOCOLS.some(p => absolute.startsWith(p))) continue;

      // Truncate extremely long URLs for safety
      if (absolute.length > 2048) {
        absolute = absolute.substring(0, 2048);
      }

      if (!urlMap.has(absolute)) {
        urlMap.set(absolute, new Set());
      }
      urlMap.get(absolute).add(a);
      seen.add(a);
    }
  }

  /* ───────── Highlighting ───────── */
  function clearHighlights() {
    // Remove all classes and badges
    const highlighted = document.querySelectorAll(
      STATUS_CLASSES.map(c => `a.${c}`).join(',')
    );
    for (const a of highlighted) {
      STATUS_CLASSES.forEach(c => a.classList.remove(c));
    }
    // Remove all badges
    const badges = document.querySelectorAll('.linkspy-badge');
    for (const b of badges) b.remove();
  }

  function getTooltip(status, code) {
    switch (status) {
      case 'broken': return "This page doesn't exist (HTTP " + code + ")";
      case 'redirect': return 'Redirects (HTTP ' + code + ')';
      case 'blocked': return "Site blocked our check — probably fine";
      case 'timeout': return "Didn't respond in time";
      case 'error': return 'Connection failed';
      default: return '';
    }
  }

  function getBadgeText(status, code) {
    switch (status) {
      case 'broken': return code === 404 ? '404' : String(code || '404');
      case 'redirect': return '→';
      case 'blocked': return '⊘';
      case 'timeout': return '⏱';
      case 'error': return '!';
      default: return '';
    }
  }

  function applyHighlight(url, result) {
    const elements = urlMap.get(url);
    if (!elements) return;

    const { status, code } = result;

    requestAnimationFrame(() => {
      for (const a of elements) {
        // Remove any existing linkspy classes
        STATUS_CLASSES.forEach(c => a.classList.remove(c));

        // Don't highlight OK links if setting is off
        if (status === 'ok' && !settings.highlightOk) continue;

        // Add status class
        a.classList.add('linkspy-' + status);

        // Remove any existing badge for this link
        const existingBadge = a.nextElementSibling;
        if (existingBadge && existingBadge.classList.contains('linkspy-badge')) {
          existingBadge.remove();
        }

        // Don't show badge for OK links
        if (status === 'ok') continue;

        // Add badge if enabled
        if (settings.showBadges) {
          injectBadge(a, status, code);
        }
      }
    });
  }

  function injectBadge(anchor, status, code) {
    const badge = document.createElement('span');
    badge.className = `linkspy-badge linkspy-badge-${status}`;
    badge.setAttribute('data-tooltip', getTooltip(status, code));
    badge.textContent = getBadgeText(status, code);

    // Dismiss button
    const dismiss = document.createElement('span');
    dismiss.className = 'linkspy-badge-dismiss';
    dismiss.textContent = '×';
    dismiss.addEventListener('click', (e) => {
      e.stopPropagation();
      e.preventDefault();
      badge.remove();
    });
    badge.appendChild(dismiss);

    // Insert after the anchor
    if (anchor.nextSibling) {
      anchor.parentNode.insertBefore(badge, anchor.nextSibling);
    } else {
      anchor.parentNode.appendChild(badge);
    }
  }

  function toggleOkHighlights(hide) {
    for (const [url, elements] of urlMap) {
      if (results[url] && results[url].status === 'ok') {
        for (const a of elements) {
          if (hide) {
            a.classList.remove('linkspy-ok');
          } else if (settings.highlightOk) {
            a.classList.add('linkspy-ok');
          }
        }
      }
    }
  }

  /* ───────── Scan ───────── */
  async function startScan() {
    if (isScanning) return;
    isScanning = true;

    // Clear previous
    clearHighlights();
    results = {};

    // Collect links
    collectLinks();

    // Get unique URLs (capped at MAX_LINKS)
    let urls = Array.from(urlMap.keys());
    let capped = 0;
    if (urls.length > MAX_LINKS) {
      capped = urls.length;
      urls = urls.slice(0, MAX_LINKS);
      // Remove excess from urlMap
      const keep = new Set(urls);
      for (const key of urlMap.keys()) {
        if (!keep.has(key)) urlMap.delete(key);
      }
    }

    totalLinks = urls.length;

    if (totalLinks === 0) {
      isScanning = false;
      if (panel) {
        panel.setComplete({ total: 0, ok: 0, redirect: 0, broken: 0, blocked: 0, timeout: 0, error: 0 });
      }
      return;
    }

    // Show panel
    if (panel) {
      panel.show();
      panel.setScanning(totalLinks, capped > 0 ? capped : 0);
    }

    // Add scanning class to all links
    for (const [, elements] of urlMap) {
      for (const a of elements) {
        a.classList.add('linkspy-scanning');
      }
    }

    // Send to background
    try {
      chrome.runtime.sendMessage({
        action: 'checkLinks',
        urls: urls,
      });
    } catch (e) {
      isScanning = false;
      console.error('[LinkSpy] Failed to send links to background:', e);
    }
  }

  function rescan() {
    isScanning = false;
    // Clear cache
    try {
      chrome.runtime.sendMessage({ action: 'clearCache' });
    } catch (e) {}
    startScan();
  }

  /* ───────── Message Handling ───────── */
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'partialResults') {
      // Apply highlights for this batch
      for (const url in message.results) {
        results[url] = message.results[url];
        applyHighlight(url, message.results[url]);

        // Remove scanning class
        const elements = urlMap.get(url);
        if (elements) {
          for (const a of elements) {
            a.classList.remove('linkspy-scanning');
          }
        }
      }

      // Update progress
      if (message.progress && panel) {
        panel.updateProgress(message.progress.checked, message.progress.total);
      }

      sendResponse({ received: true });
      return false;
    }

    if (message.action === 'scanComplete') {
      isScanning = false;

      // Apply any remaining results
      for (const url in message.results) {
        if (!results[url]) {
          results[url] = message.results[url];
          applyHighlight(url, message.results[url]);
        }
        // Remove scanning class
        const elements = urlMap.get(url);
        if (elements) {
          for (const a of elements) {
            a.classList.remove('linkspy-scanning');
          }
        }
      }

      // Update panel stats
      if (panel) {
        panel.setComplete(message.stats);
      }

      sendResponse({ received: true });
      return false;
    }

    // Messages from popup
    if (message.action === 'getStats') {
      const stats = { total: 0, ok: 0, redirect: 0, broken: 0, blocked: 0, timeout: 0, error: 0 };
      for (const url in results) {
        stats.total++;
        const s = results[url].status;
        if (s in stats) stats[s]++;
      }
      sendResponse({ stats, isScanning, totalLinks });
      return false;
    }

    if (message.action === 'rescan') {
      rescan();
      sendResponse({ started: true });
      return false;
    }

    if (message.action === 'scrollToBroken') {
      const broken = document.querySelector('a.linkspy-broken');
      if (broken) {
        broken.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // Flash effect
        broken.style.outline = '2px solid #f87171';
        broken.style.outlineOffset = '2px';
        setTimeout(() => {
          broken.style.outline = '';
          broken.style.outlineOffset = '';
        }, 2000);
      }
      sendResponse({ found: !!broken });
      return false;
    }

    if (message.action === 'updateSettings') {
      const newSettings = message.settings;
      if (newSettings.showBadges !== undefined) {
        settings.showBadges = newSettings.showBadges;
        if (!settings.showBadges) {
          // Remove all badges
          document.querySelectorAll('.linkspy-badge').forEach(b => b.remove());
        } else {
          // Re-add badges
          for (const url in results) {
            if (results[url].status !== 'ok') {
              applyHighlight(url, results[url]);
            }
          }
        }
      }
      if (newSettings.highlightOk !== undefined) {
        settings.highlightOk = newSettings.highlightOk;
        for (const [url, elements] of urlMap) {
          if (results[url] && results[url].status === 'ok') {
            for (const a of elements) {
              if (settings.highlightOk) {
                a.classList.add('linkspy-ok');
              } else {
                a.classList.remove('linkspy-ok');
              }
            }
          }
        }
      }
      if (newSettings.autoScan !== undefined) {
        settings.autoScan = newSettings.autoScan;
      }
      sendResponse({ updated: true });
      return false;
    }

    if (message.action === 'showPanel') {
      if (panel) panel.show();
      sendResponse({ shown: true });
      return false;
    }

    if (message.action === 'triggerScan') {
      startScan();
      sendResponse({ started: true });
      return false;
    }

    return false;
  });

  /* ───────── MutationObserver for dynamic links ───────── */
  function setupMutationObserver() {
    const observer = new MutationObserver((mutations) => {
      if (mutationTimer) clearTimeout(mutationTimer);
      mutationTimer = setTimeout(() => {
        const newUrls = [];

        for (const mutation of mutations) {
          for (const node of mutation.addedNodes) {
            if (node.nodeType !== 1) continue;

            // Check the node itself
            const anchors = node.tagName === 'A' ? [node] : [];
            // Check descendants
            if (node.querySelectorAll) {
              anchors.push(...node.querySelectorAll('a[href]'));
            }

            for (const a of anchors) {
              const href = (a.getAttribute('href') || '').trim();
              if (!href || SKIP_PREFIXES.some(p => href.startsWith(p))) continue;

              let absolute;
              try {
                absolute = new URL(href, window.location.href).href;
              } catch (e) { continue; }

              if (SKIP_PROTOCOLS.some(p => absolute.startsWith(p))) continue;

              // Already tracked?
              if (urlMap.has(absolute)) {
                urlMap.get(absolute).add(a);
                // If we already have a result, apply it
                if (results[absolute]) {
                  applyHighlight(absolute, results[absolute]);
                }
              } else {
                // New URL
                urlMap.set(absolute, new Set([a]));
                newUrls.push(absolute);
              }
            }
          }
        }

        // Send new URLs for checking
        for (const url of newUrls) {
          try {
            chrome.runtime.sendMessage({ action: 'checkSingle', url });
          } catch (e) {}
        }
      }, 500);
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true,
    });
  }

  /* ───────── SPA Navigation Detection ───────── */
  function setupSPADetection() {
    // Intercept pushState and replaceState
    const origPushState = history.pushState;
    const origReplaceState = history.replaceState;

    history.pushState = function (...args) {
      origPushState.apply(this, args);
      onSPANavigation();
    };

    history.replaceState = function (...args) {
      origReplaceState.apply(this, args);
      onSPANavigation();
    };

    window.addEventListener('popstate', onSPANavigation);
  }

  function onSPANavigation() {
    if (spaTimer) clearTimeout(spaTimer);
    spaTimer = setTimeout(() => {
      if (settings.autoScan) {
        isScanning = false;
        startScan();
      }
    }, 1000);
  }

  /* ───────── Initialize ───────── */
  async function init() {
    await loadSettings();

    // Create panel
    if (typeof window.__LinkSpyPanel === 'function') {
      panel = new window.__LinkSpyPanel();
      await panel.init();
      panel.onRescan = rescan;
      panel.onToggleOk = toggleOkHighlights;
    }

    // Setup observers
    setupMutationObserver();
    setupSPADetection();

    // Auto-scan if enabled
    if (settings.autoScan) {
      startScan();
    }
  }

  // Wait for panel.js to load (it's listed before content.js in manifest)
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    // Small delay to ensure panel.js has executed
    setTimeout(init, 50);
  }
})();
