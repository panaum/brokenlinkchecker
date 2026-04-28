/**
 * LinkSpy — Popup Script
 * Manages the toolbar popup UI, settings toggles,
 * and communication with the active tab's content script.
 */

;(function () {
  'use strict';

  /* ───────── DOM References ───────── */
  const els = {
    total: document.getElementById('popup-total'),
    ok: document.getElementById('popup-ok'),
    redirect: document.getElementById('popup-redirect'),
    broken: document.getElementById('popup-broken'),
    blocked: document.getElementById('popup-blocked'),
    brokenRow: document.getElementById('popup-broken-row'),
    scanningMsg: document.getElementById('popup-scanning-msg'),
    noPage: document.getElementById('popup-no-page'),
    statsSection: document.getElementById('popup-stats-section'),
    scanBtn: document.getElementById('popup-scan-btn'),
    scrollBroken: document.getElementById('popup-scroll-broken'),
    showPanel: document.getElementById('popup-show-panel'),
    toggleAutoScan: document.getElementById('toggle-autoscan'),
    toggleBadges: document.getElementById('toggle-badges'),
    toggleHighlightOk: document.getElementById('toggle-highlight-ok'),
  };

  /* ───────── Get Active Tab ───────── */
  async function getActiveTab() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    return tab;
  }

  /* ───────── Send Message to Content Script ───────── */
  async function sendToContent(action, data = {}) {
    const tab = await getActiveTab();
    if (!tab || !tab.id) return null;

    // Skip chrome:// and other restricted pages
    if (!tab.url || !tab.url.startsWith('http')) return null;

    try {
      return await chrome.tabs.sendMessage(tab.id, { action, ...data });
    } catch (e) {
      return null;
    }
  }

  /* ───────── Load Stats ───────── */
  async function loadStats() {
    const tab = await getActiveTab();

    // Check if it's a valid web page
    if (!tab || !tab.url || !tab.url.startsWith('http')) {
      showNoPage();
      return;
    }

    const response = await sendToContent('getStats');

    if (!response) {
      showNoPage();
      return;
    }

    if (response.isScanning) {
      showScanning();
      return;
    }

    showStats(response.stats);
  }

  function showNoPage() {
    els.noPage.style.display = '';
    document.getElementById('popup-stats').style.display = 'none';
    els.scanningMsg.style.display = 'none';
    els.scrollBroken.style.display = 'none';
  }

  function showScanning() {
    els.noPage.style.display = 'none';
    document.getElementById('popup-stats').style.display = 'none';
    els.scanningMsg.style.display = 'flex';
  }

  function showStats(stats) {
    els.noPage.style.display = 'none';
    els.scanningMsg.style.display = 'none';
    document.getElementById('popup-stats').style.display = '';

    els.total.textContent = stats.total || 0;
    els.ok.textContent = stats.ok || 0;
    els.redirect.textContent = stats.redirect || 0;

    const brokenCount = stats.broken || 0;
    els.broken.textContent = brokenCount;
    const blockedCount = (stats.blocked || 0) + (stats.timeout || 0) + (stats.error || 0);
    els.blocked.textContent = blockedCount;

    if (brokenCount > 0) {
      els.brokenRow.classList.add('has-broken');
      els.broken.classList.add('has-broken');
      els.scrollBroken.style.display = '';
    } else {
      els.brokenRow.classList.remove('has-broken');
      els.broken.classList.remove('has-broken');
      els.scrollBroken.style.display = 'none';
    }
  }

  /* ───────── Load Settings ───────── */
  async function loadSettings() {
    try {
      const data = await chrome.storage.local.get([
        'autoScan',
        'showBadges',
        'highlightOk',
      ]);

      els.toggleAutoScan.checked =
        data.autoScan !== undefined ? data.autoScan : true;
      els.toggleBadges.checked =
        data.showBadges !== undefined ? data.showBadges : true;
      els.toggleHighlightOk.checked =
        data.highlightOk !== undefined ? data.highlightOk : false;
    } catch (e) {}
  }

  /* ───────── Save Setting ───────── */
  async function saveSetting(key, value) {
    try {
      await chrome.storage.local.set({ [key]: value });
    } catch (e) {}

    // Also notify content script to apply immediately
    await sendToContent('updateSettings', {
      settings: { [key]: value },
    });
  }

  /* ───────── Event Listeners ───────── */

  // Scan button
  els.scanBtn.addEventListener('click', async () => {
    els.scanBtn.textContent = '⟳ Scanning...';
    els.scanBtn.disabled = true;
    await sendToContent('rescan');
    showScanning();
    // Re-enable after a delay
    setTimeout(() => {
      els.scanBtn.textContent = '⟳ Scan this page';
      els.scanBtn.disabled = false;
      loadStats();
    }, 3000);
  });

  // Scroll to broken
  els.scrollBroken.addEventListener('click', async () => {
    await sendToContent('scrollToBroken');
    window.close(); // Close popup so user sees the page
  });

  // Show panel
  els.showPanel.addEventListener('click', async () => {
    await sendToContent('showPanel');
    window.close();
  });

  // Toggle: Auto-scan
  els.toggleAutoScan.addEventListener('change', (e) => {
    saveSetting('autoScan', e.target.checked);
  });

  // Toggle: Show badges
  els.toggleBadges.addEventListener('change', (e) => {
    saveSetting('showBadges', e.target.checked);
  });

  // Toggle: Highlight working
  els.toggleHighlightOk.addEventListener('change', (e) => {
    saveSetting('highlightOk', e.target.checked);
  });

  /* ───────── Initialize ───────── */
  loadSettings();
  loadStats();
})();
