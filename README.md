# LinkSpy — Broken Link Checker

A production-ready, full-stack broken link checker that crawls any webpage, extracts every link across all page zones (nav, header, footer, CTAs, body text), checks each link's HTTP status, and returns a beautiful visual report.

## Tech Stack

### Backend
- **Python 3.11+** with **FastAPI** (REST API + SSE streaming)
- **Playwright** (headless Chromium for JS-heavy page rendering)
- **BeautifulSoup4 + lxml** (DOM parsing and zone extraction)
- **httpx\[http2\]** (async HTTP link checking with redirect tracking)
- **asyncio** with semaphore-based concurrency (20 concurrent checks)
- **Pydantic v2** (request/response validation)

### Frontend
- **Next.js 14** (App Router) with **TypeScript**
- **Tailwind CSS v4** (utility-first styling)
- **Framer Motion** (animations)
- **Lucide React** (icons)
- **Google Font: Poppins**

---

## Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+
- npm

### Backend Setup

```bash
cd backend
pip install -r requirements.txt
playwright install chromium
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The app will be available at `http://localhost:3000`.

---

## Environment Variables

### Backend (`backend/.env`)
```
PORT=8000
```

### Frontend (`frontend/.env.local`)
```
BACKEND_URL=http://localhost:8000
NEXT_PUBLIC_APP_NAME=LinkSpy
```

---

## API Endpoints

### `GET /scan?url=<encoded_url>`
SSE endpoint that streams scan progress and results.

**Event types:**
- `{"type": "progress", "message": "...", "percent": 0-100}`
- `{"type": "result", "data": [...LinkResult...]}`
- `{"type": "error", "message": "..."}`

### `GET /health`
Health check endpoint. Returns `{"status": "ok"}`.

---

## Features

- 🔍 **Full page crawling** — Renders JS-heavy pages with Playwright
- 🗂️ **Zone detection** — Categorizes links by Navigation, Header, Footer, CTA, Body text
- ⚡ **Concurrent checking** — 20 simultaneous HTTP checks with HEAD/GET fallback
- 📊 **Real-time streaming** — SSE-based progress updates during scan
- 🎨 **Beautiful UI** — Glass-morphism design with gradient accents
- 📋 **CSV Export** — Download results as CSV
- 🔄 **Sortable table** — Click any column header to sort
- 📱 **Responsive** — Works on mobile, tablet, and desktop
