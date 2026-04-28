/**
 * LinkSpy — Background Service Worker
 * Handles all HTTP link checking to bypass CORS restrictions.
 * Processes links in batches with throttling and caching.
 */

/* ───────── Constants ───────── */
const BATCH_SIZE = 10;
const BATCH_DELAY = 200;
const REQUEST_TIMEOUT = 8000;
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

/* ───────── URL Status Classification ───────── */
function classifyStatus(code) {
  if (code >= 200 && code <= 299) return 'ok';
  if (code >= 300 && code <= 399) return 'redirect';
  if ([401, 403, 429, 999].includes(code)) return 'blocked';
  if ([404, 410].includes(code)) return 'broken';
  if (code >= 500) return 'error';
  return 'error';
}

/* ───────── Single URL Check ───────── */
async function checkUrl(url) {
  // Skip non-http(s) URLs
  if (!/^https?:\/\//i.test(url)) {
    return { status: 'error', code: 0 };
  }

  try {
    // Try HEAD first
    let response = await fetch(url, {
      method: 'HEAD',
      redirect: 'follow',
      signal: AbortSignal.timeout(REQUEST_TIMEOUT),
    });

    // If HEAD returns 405, retry with GET
    if (response.status === 405) {
      response = await fetch(url, {
        method: 'GET',
        redirect: 'follow',
        signal: AbortSignal.timeout(REQUEST_TIMEOUT),
      });
    }

    const status = classifyStatus(response.status);
    return { status, code: response.status };
  } catch (err) {
    // Timeout
    if (err.name === 'AbortError' || err.name === 'TimeoutError') {
      return { status: 'timeout', code: 0 };
    }

    // TypeError typically means CORS or network failure
    // Try GET as fallback
    if (err instanceof TypeError) {
      try {
        const response = await fetch(url, {
          method: 'GET',
          redirect: 'follow',
          signal: AbortSignal.timeout(REQUEST_TIMEOUT),
        });
        const status = classifyStatus(response.status);
        return { status, code: response.status };
      } catch (fallbackErr) {
        if (
          fallbackErr.name === 'AbortError' ||
          fallbackErr.name === 'TimeoutError'
        ) {
          return { status: 'timeout', code: 0 };
        }
        return { status: 'error', code: 0 };
      }
    }

    return { status: 'error', code: 0 };
  }
}

/* ───────── Cache Helpers ───────── */
async function getCachedResult(url) {
  try {
    const data = await chrome.storage.session.get(url);
    if (data[url]) {
      const entry = data[url];
      if (Date.now() - entry.checkedAt < CACHE_TTL) {
        return entry;
      }
    }
  } catch (e) {
    // session storage may not be available
  }
  return null;
}

async function setCachedResult(url, result) {
  try {
    await chrome.storage.session.set({
      [url]: { ...result, checkedAt: Date.now() },
    });
  } catch (e) {
    // ignore
  }
}

/* ───────── Batch Processing ───────── */
async function processLinks(urls, senderTabId) {
  const allResults = {};
  const total = urls.length;
  let checked = 0;

  // Process in batches
  for (let i = 0; i < urls.length; i += BATCH_SIZE) {
    const batch = urls.slice(i, i + BATCH_SIZE);

    const batchResults = await Promise.all(
      batch.map(async (url) => {
        // Check cache first
        const cached = await getCachedResult(url);
        if (cached) {
          return { url, result: { status: cached.status, code: cached.code } };
        }

        const result = await checkUrl(url);
        await setCachedResult(url, result);
        return { url, result };
      })
    );

    // Collect batch results
    const partialResults = {};
    for (const { url, result } of batchResults) {
      allResults[url] = result;
      partialResults[url] = result;
    }

    checked += batch.length;

    // Send incremental update to content script
    try {
      await chrome.tabs.sendMessage(senderTabId, {
        action: 'partialResults',
        results: partialResults,
        progress: { checked, total },
      });
    } catch (e) {
      // Tab may have been closed
      return;
    }

    // Delay between batches (skip after last batch)
    if (i + BATCH_SIZE < urls.length) {
      await new Promise((r) => setTimeout(r, BATCH_DELAY));
    }
  }

  // Compute final stats
  const stats = { total: 0, ok: 0, redirect: 0, broken: 0, blocked: 0, timeout: 0, error: 0 };
  for (const url in allResults) {
    stats.total++;
    const s = allResults[url].status;
    if (s in stats) stats[s]++;
  }

  // Send final complete message
  try {
    await chrome.tabs.sendMessage(senderTabId, {
      action: 'scanComplete',
      results: allResults,
      stats,
    });
  } catch (e) {
    // Tab closed
  }
}

/* ───────── Message Listener ───────── */
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'checkLinks') {
    const tabId = sender.tab?.id;
    if (tabId == null) {
      sendResponse({ error: 'No tab ID' });
      return false;
    }
    // Start processing asynchronously
    processLinks(message.urls, tabId);
    sendResponse({ started: true, total: message.urls.length });
    return false; // synchronous response
  }

  if (message.action === 'checkSingle') {
    const tabId = sender.tab?.id;
    // Check a single URL
    (async () => {
      const cached = await getCachedResult(message.url);
      if (cached) {
        try {
          await chrome.tabs.sendMessage(tabId, {
            action: 'partialResults',
            results: { [message.url]: { status: cached.status, code: cached.code } },
            progress: null,
          });
        } catch (e) {}
        return;
      }

      const result = await checkUrl(message.url);
      await setCachedResult(message.url, result);

      try {
        await chrome.tabs.sendMessage(tabId, {
          action: 'partialResults',
          results: { [message.url]: result },
          progress: null,
        });
      } catch (e) {}
    })();
    sendResponse({ started: true });
    return false;
  }

  if (message.action === 'clearCache') {
    chrome.storage.session.clear();
    sendResponse({ cleared: true });
    return false;
  }

  return false;
});
