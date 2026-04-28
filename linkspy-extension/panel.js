/**
 * LinkSpy — Floating Panel (Shadow DOM isolated)
 * Creates a draggable summary panel injected into the page.
 * All styles are encapsulated via Shadow DOM.
 */

/* ───────── Panel CSS (embedded for Shadow DOM) ───────── */
const PANEL_STYLES = `
*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

:host {
  all: initial;
  position: fixed !important;
  z-index: 2147483647 !important;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Poppins', sans-serif;
}

#linkspy-panel {
  width: 220px;
  background: rgba(10, 6, 18, 0.95);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 12px;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Poppins', sans-serif;
  color: white;
  overflow: hidden;
  transition: opacity 0.2s ease;
  user-select: none;
}

#linkspy-panel.linkspy-minimized #linkspy-panel-body,
#linkspy-panel.linkspy-minimized #linkspy-panel-footer {
  display: none;
}

#linkspy-panel-header {
  height: 36px;
  background: linear-gradient(132deg, rgb(65,0,153) 0%, rgb(86,16,96) 100%);
  border-radius: 12px 12px 0 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 10px;
  cursor: grab;
}
#linkspy-panel-header:active { cursor: grabbing; }

#linkspy-panel.linkspy-minimized #linkspy-panel-header {
  border-radius: 12px;
}

#linkspy-panel-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: white;
  pointer-events: none;
}

#linkspy-logo svg {
  width: 16px;
  height: 16px;
  display: block;
}

#linkspy-panel-controls {
  display: flex;
  align-items: center;
  gap: 4px;
}

#linkspy-panel-controls button {
  width: 18px;
  height: 18px;
  background: rgba(255,255,255,0.1);
  border-radius: 4px;
  color: white;
  border: none;
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s ease;
  font-family: inherit;
  padding: 0;
}
#linkspy-panel-controls button:hover {
  background: rgba(255,255,255,0.2);
}

#linkspy-panel-body {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

#linkspy-scanning {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}

.linkspy-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255,255,255,0.15);
  border-top: 2px solid #a855f7;
  border-radius: 50%;
  animation: linkspy-spin 0.7s linear infinite;
  flex-shrink: 0;
}
@keyframes linkspy-spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

#linkspy-scan-msg {
  font-size: 11px;
  color: rgba(255,255,255,0.6);
}

#linkspy-stats {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.linkspy-stat-row {
  display: flex;
  align-items: center;
  font-size: 12px;
  color: rgba(255,255,255,0.75);
  padding: 3px 6px;
  border-radius: 6px;
  transition: background 0.2s ease;
}

.linkspy-stat-row#lsp-total {
  margin-bottom: 2px;
  padding-bottom: 6px;
  border-bottom: 0.5px solid rgba(255,255,255,0.08);
}

.lsp-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-right: 8px;
  flex-shrink: 0;
}
.lsp-label { flex: 1; }
.lsp-val {
  font-weight: 600;
  font-size: 14px;
  color: white;
  min-width: 24px;
  text-align: right;
}

.linkspy-stat-row.lsp-broken-highlight {
  background: rgba(248,113,113,0.08);
}
.lsp-broken-num.lsp-has-broken {
  color: #f87171;
}

#linkspy-progress-wrap {
  height: 3px;
  background: rgba(255,255,255,0.1);
  border-radius: 2px;
  overflow: hidden;
}
#linkspy-progress-bar {
  height: 100%;
  width: 0%;
  background: linear-gradient(90deg, rgb(65,0,153), rgb(138,26,155));
  border-radius: 2px;
  transition: width 0.3s ease;
}
#linkspy-progress-label {
  font-size: 10px;
  color: rgba(255,255,255,0.4);
  text-align: center;
  margin-top: 2px;
}

.linkspy-hidden { display: none !important; }

#linkspy-panel-footer {
  border-top: 0.5px solid rgba(255,255,255,0.08);
  padding: 8px 12px;
  display: flex;
  gap: 6px;
}
#linkspy-panel-footer button {
  font-size: 11px;
  flex: 1;
  background: rgba(255,255,255,0.06);
  border: 0.5px solid rgba(255,255,255,0.12);
  border-radius: 6px;
  color: white;
  padding: 5px 0;
  cursor: pointer;
  transition: background 0.15s ease;
  font-family: inherit;
}
#linkspy-panel-footer button:hover {
  background: rgba(255,255,255,0.12);
}

#linkspy-cap-notice {
  font-size: 10px;
  color: rgba(255,255,255,0.35);
  text-align: center;
  padding: 0 6px 6px;
}
`;

/* ───────── SVG Logo ───────── */
const LOGO_SVG = `<svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M6.5 9.5L9.5 6.5" stroke="url(#lg1)" stroke-width="1.5" stroke-linecap="round"/>
  <path d="M9.17 7.17L10.83 5.5A2 2 0 1 0 8 2.67L6.33 4.33" stroke="url(#lg1)" stroke-width="1.5" stroke-linecap="round"/>
  <path d="M6.83 8.83L5.17 10.5A2 2 0 1 0 8 13.33l1.67-1.67" stroke="url(#lg1)" stroke-width="1.5" stroke-linecap="round"/>
  <defs>
    <linearGradient id="lg1" x1="2" y1="2" x2="14" y2="14">
      <stop stop-color="#c084fc"/><stop offset="1" stop-color="#e879f9"/>
    </linearGradient>
  </defs>
</svg>`;

/* ───────── Panel Class ───────── */
class LinkSpyPanel {
  constructor() {
    this.host = null;
    this.shadow = null;
    this.panel = null;
    this.isDragging = false;
    this.dragOffset = { x: 0, y: 0 };
    this.position = { top: 20, left: window.innerWidth - 240 };
    this.isMinimized = false;
    this.isHidden = false;
    this.hideOk = false;
    this.onRescan = null;
    this.onToggleOk = null;
  }

  async init() {
    // Load saved state
    try {
      const data = await chrome.storage.local.get(['panelPosition', 'panelMinimized']);
      if (data.panelPosition) {
        this.position = data.panelPosition;
      }
      if (data.panelMinimized) {
        this.isMinimized = data.panelMinimized;
      }
    } catch (e) {}

    this._createDOM();
    this._setupDrag();
    this._setupControls();
    this._applyPosition();
  }

  _createDOM() {
    // Shadow DOM host
    this.host = document.createElement('linkspy-panel');
    this.host.style.cssText = `
      position: fixed !important;
      z-index: 2147483647 !important;
      top: 0; left: 0;
      pointer-events: none;
    `;
    document.documentElement.appendChild(this.host);

    this.shadow = this.host.attachShadow({ mode: 'closed' });

    // Inject styles
    const style = document.createElement('style');
    style.textContent = PANEL_STYLES;
    this.shadow.appendChild(style);

    // Panel HTML
    const wrapper = document.createElement('div');
    wrapper.innerHTML = `
      <div id="linkspy-panel" style="position:fixed; pointer-events:auto;" ${this.isMinimized ? 'class="linkspy-minimized"' : ''}>
        <div id="linkspy-panel-header">
          <div id="linkspy-panel-title">
            <div id="linkspy-logo">${LOGO_SVG}</div>
            <span>LinkSpy</span>
          </div>
          <div id="linkspy-panel-controls">
            <button id="linkspy-minimize" title="Minimize">−</button>
            <button id="linkspy-close" title="Close">×</button>
          </div>
        </div>

        <div id="linkspy-panel-body">
          <div id="linkspy-scanning">
            <div class="linkspy-spinner"></div>
            <span id="linkspy-scan-msg">Scanning links...</span>
          </div>

          <div id="linkspy-stats" class="linkspy-hidden">
            <div class="linkspy-stat-row" id="lsp-total">
              <span class="lsp-label">Total</span>
              <span class="lsp-val" id="lsp-total-val">—</span>
            </div>
            <div class="linkspy-stat-row" id="lsp-ok">
              <span class="lsp-dot" style="background:#4ade80"></span>
              <span class="lsp-label">Working</span>
              <span class="lsp-val" id="lsp-ok-val">—</span>
            </div>
            <div class="linkspy-stat-row" id="lsp-redirect">
              <span class="lsp-dot" style="background:#fb923c"></span>
              <span class="lsp-label">Redirected</span>
              <span class="lsp-val" id="lsp-redirect-val">—</span>
            </div>
            <div class="linkspy-stat-row" id="lsp-broken">
              <span class="lsp-dot" style="background:#f87171"></span>
              <span class="lsp-label">Broken</span>
              <span class="lsp-val lsp-broken-num" id="lsp-broken-val">—</span>
            </div>
            <div class="linkspy-stat-row" id="lsp-blocked">
              <span class="lsp-dot" style="background:#e879f9"></span>
              <span class="lsp-label">Can't verify</span>
              <span class="lsp-val" id="lsp-blocked-val">—</span>
            </div>
          </div>

          <div id="linkspy-progress-wrap">
            <div id="linkspy-progress-bar"></div>
          </div>
          <div id="linkspy-progress-label"></div>
        </div>

        <div id="linkspy-panel-footer">
          <button id="linkspy-rescan">↺ Rescan</button>
          <button id="linkspy-hide-ok">Hide working</button>
        </div>
      </div>
    `;

    this.shadow.appendChild(wrapper.firstElementChild);
    this.panel = this.shadow.getElementById('linkspy-panel');
  }

  _applyPosition() {
    // Clamp to viewport
    const maxLeft = window.innerWidth - 230;
    const maxTop = window.innerHeight - 60;
    this.position.left = Math.max(0, Math.min(this.position.left, maxLeft));
    this.position.top = Math.max(0, Math.min(this.position.top, maxTop));

    this.panel.style.left = this.position.left + 'px';
    this.panel.style.top = this.position.top + 'px';
  }

  _setupDrag() {
    const header = this.shadow.getElementById('linkspy-panel-header');

    const onMouseDown = (e) => {
      // Don't drag if clicking buttons
      if (e.target.tagName === 'BUTTON') return;
      this.isDragging = true;
      const rect = this.panel.getBoundingClientRect();
      this.dragOffset.x = e.clientX - rect.left;
      this.dragOffset.y = e.clientY - rect.top;
      e.preventDefault();
    };

    const onMouseMove = (e) => {
      if (!this.isDragging) return;
      const x = e.clientX - this.dragOffset.x;
      const y = e.clientY - this.dragOffset.y;
      // Clamp
      this.position.left = Math.max(0, Math.min(x, window.innerWidth - 230));
      this.position.top = Math.max(0, Math.min(y, window.innerHeight - 60));
      this.panel.style.left = this.position.left + 'px';
      this.panel.style.top = this.position.top + 'px';
    };

    const onMouseUp = () => {
      if (!this.isDragging) return;
      this.isDragging = false;
      // Save position
      try {
        chrome.storage.local.set({ panelPosition: this.position });
      } catch (e) {}
    };

    header.addEventListener('mousedown', onMouseDown);
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }

  _setupControls() {
    // Minimize
    const minBtn = this.shadow.getElementById('linkspy-minimize');
    minBtn.addEventListener('click', () => {
      this.isMinimized = !this.isMinimized;
      this.panel.classList.toggle('linkspy-minimized', this.isMinimized);
      minBtn.textContent = this.isMinimized ? '+' : '−';
      try {
        chrome.storage.local.set({ panelMinimized: this.isMinimized });
      } catch (e) {}
    });

    // Close
    this.shadow.getElementById('linkspy-close').addEventListener('click', () => {
      this.hide();
    });

    // Rescan
    this.shadow.getElementById('linkspy-rescan').addEventListener('click', () => {
      if (this.onRescan) this.onRescan();
    });

    // Hide OK
    const hideBtn = this.shadow.getElementById('linkspy-hide-ok');
    hideBtn.addEventListener('click', () => {
      this.hideOk = !this.hideOk;
      hideBtn.textContent = this.hideOk ? 'Show all' : 'Hide working';
      if (this.onToggleOk) this.onToggleOk(this.hideOk);
    });
  }

  /* ───── Public API ───── */

  show() {
    this.isHidden = false;
    if (this.host) this.host.style.display = '';
  }

  hide() {
    this.isHidden = true;
    if (this.host) this.host.style.display = 'none';
  }

  destroy() {
    if (this.host && this.host.parentNode) {
      this.host.parentNode.removeChild(this.host);
    }
  }

  setScanning(totalLinks, capped) {
    const scanning = this.shadow.getElementById('linkspy-scanning');
    const stats = this.shadow.getElementById('linkspy-stats');
    const scanMsg = this.shadow.getElementById('linkspy-scan-msg');
    const progressWrap = this.shadow.getElementById('linkspy-progress-wrap');
    const progressLabel = this.shadow.getElementById('linkspy-progress-label');
    const capNotice = this.shadow.getElementById('linkspy-cap-notice');

    scanning.style.display = 'flex';
    stats.classList.add('linkspy-hidden');
    progressWrap.style.display = '';
    progressLabel.style.display = '';

    let msg = `Scanning ${totalLinks} links...`;
    scanMsg.textContent = msg;

    // Remove old cap notice
    if (capNotice) capNotice.remove();

    if (capped) {
      const notice = document.createElement('div');
      notice.id = 'linkspy-cap-notice';
      notice.textContent = `Showing first 500 of ${capped} links`;
      this.shadow.getElementById('linkspy-panel-body').appendChild(notice);
    }

    this._updateProgress(0, totalLinks);
  }

  updateProgress(checked, total) {
    this._updateProgress(checked, total);
  }

  _updateProgress(checked, total) {
    const bar = this.shadow.getElementById('linkspy-progress-bar');
    const label = this.shadow.getElementById('linkspy-progress-label');
    const pct = total > 0 ? (checked / total) * 100 : 0;
    bar.style.width = pct + '%';
    label.textContent = `Checked ${checked} of ${total}`;
  }

  setComplete(stats) {
    const scanning = this.shadow.getElementById('linkspy-scanning');
    const statsEl = this.shadow.getElementById('linkspy-stats');
    const progressWrap = this.shadow.getElementById('linkspy-progress-wrap');
    const progressLabel = this.shadow.getElementById('linkspy-progress-label');

    scanning.style.display = 'none';
    statsEl.classList.remove('linkspy-hidden');
    progressWrap.style.display = 'none';
    progressLabel.style.display = 'none';

    this.shadow.getElementById('lsp-total-val').textContent = stats.total || 0;
    this.shadow.getElementById('lsp-ok-val').textContent = stats.ok || 0;
    this.shadow.getElementById('lsp-redirect-val').textContent = stats.redirect || 0;

    const brokenVal = this.shadow.getElementById('lsp-broken-val');
    brokenVal.textContent = stats.broken || 0;
    const brokenRow = this.shadow.getElementById('lsp-broken');
    if (stats.broken > 0) {
      brokenVal.classList.add('lsp-has-broken');
      brokenRow.classList.add('lsp-broken-highlight');
    } else {
      brokenVal.classList.remove('lsp-has-broken');
      brokenRow.classList.remove('lsp-broken-highlight');
    }

    const blockedCount = (stats.blocked || 0) + (stats.timeout || 0) + (stats.error || 0);
    this.shadow.getElementById('lsp-blocked-val').textContent = blockedCount;
  }

  updateStats(results) {
    const stats = { total: 0, ok: 0, redirect: 0, broken: 0, blocked: 0, timeout: 0, error: 0 };
    for (const url in results) {
      stats.total++;
      const s = results[url].status;
      if (s in stats) stats[s]++;
    }
    this.setComplete(stats);
  }
}

// Expose globally for content.js
window.__LinkSpyPanel = LinkSpyPanel;
