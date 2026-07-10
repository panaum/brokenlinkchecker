"""
Active submission executor — the one place a form is actually submitted.

Everything risky is here, and it only ever carries out a plan that
active_submission.plan_submission produced (which refuses payment forms and
never fills honeypots). This file adds the live rails:

  - EXACTLY ONCE, enforced at runtime by SubmitGuard: a second submit raises.
  - The tracking-event observer is injected BEFORE the click, so we can report
    whether a conversion event fired (closing the loop with the Phase 5 audit:
    "the form works AND the event fires").
  - Navigation and the resulting status / thank-you page are recorded.

The executor needs a real browser, so it is not in the mocked test suite;
SubmitGuard and the observer script ARE unit-tested, and the whole path is
verified against a local fixture that posts to a throwaway endpoint — never a
client's form.
"""
import re
import time

from active_submission import plan_submission, default_test_email, TEST_VALUE


class SubmitGuard:
    """One submission per run, enforced. The second call raises rather than
    silently double-posting to a client's CRM."""

    def __init__(self):
        self._fired = False

    @property
    def fired(self) -> bool:
        return self._fired

    def fire(self, action):
        if self._fired:
            raise RuntimeError("SubmitGuard: a submission was already fired this run")
        self._fired = True
        return action()


# Wraps gtag / fbq / dataLayer.push to RECORD calls. It never fires an event —
# it observes the ones the form's own submit handler fires.
TRACKING_OBSERVER_JS = r"""
() => {
  if (window.__linkspy_obs) return;
  window.__linkspy_obs = true;
  window.__linkspy_events = [];
  const rec = (src, args) => {
    try { window.__linkspy_events.push({ src, arg: JSON.stringify(args).slice(0, 300) }); }
    catch (e) { window.__linkspy_events.push({ src, arg: '<unserialisable>' }); }
  };
  const wrap = (holder, name, label) => {
    try {
      const orig = holder && holder[name];
      if (typeof orig === 'function') {
        holder[name] = function () { rec(label, [].slice.call(arguments)); return orig.apply(this, arguments); };
      }
    } catch (e) {}
  };
  wrap(window, 'gtag', 'gtag');
  wrap(window, 'fbq', 'fbq');
  try {
    if (window.dataLayer && typeof window.dataLayer.push === 'function') {
      const o = window.dataLayer.push.bind(window.dataLayer);
      window.dataLayer.push = function () { rec('dataLayer', [].slice.call(arguments)); return o.apply(this, arguments); };
    }
  } catch (e) {}
  try {
    if (window.ttq && typeof window.ttq.track === 'function') {
      const o = window.ttq.track.bind(window.ttq);
      window.ttq.track = function () { rec('ttq', [].slice.call(arguments)); return o.apply(this, arguments); };
    }
  } catch (e) {}
}
"""

# Reads the live fields of one form: type/name/id + computed visibility and size,
# plus the srcs of any iframe inside it (for payment-iframe detection). READ ONLY.
_COLLECT_ONE_FORM_JS = r"""
(sel) => {
  const form = document.querySelector(sel);
  if (!form) return null;
  const fs = getComputedStyle(form), fr = form.getBoundingClientRect();
  const form_visible = fs.display !== 'none' && fs.visibility !== 'hidden'
                       && parseFloat(fs.opacity || '1') > 0 && fr.width > 1 && fr.height > 1;
  const fields = Array.from(form.querySelectorAll('input, textarea, select')).map((el) => {
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    const visible = s.display !== 'none' && s.visibility !== 'hidden'
                    && parseFloat(s.opacity || '1') > 0;
    return {
      tag: el.tagName.toLowerCase(),
      type: (el.getAttribute('type') || '').toLowerCase(),
      name: el.getAttribute('name') || '',
      id: el.id || '',
      placeholder: el.getAttribute('placeholder') || '',
      autocomplete: el.getAttribute('autocomplete') || '',
      required: !!el.required,
      visible: visible,
      width: Math.round(r.width),
      height: Math.round(r.height),
    };
  });
  const iframes = Array.from(form.querySelectorAll('iframe')).map((f) => f.getAttribute('src') || '');
  return { fields, iframes, form_visible };
}
"""


def _thankyou_detected(before_url: str, after_url: str, body_text: str) -> bool:
    """A redirect to a new URL, or thank-you wording appearing on the page."""
    if after_url and after_url != before_url:
        if re.search(r"(thank|confirm|success|received|submitted)", after_url, re.I):
            return True
    if body_text and re.search(
            r"(thank you|thanks for|we.ll be in touch|message (was )?(sent|received)|"
            r"submission received|we have received)", body_text, re.I):
        return True
    return False


def build_plan_for_live_form(collected: dict, site_url: str, test_email: str = None) -> dict:
    """Turn the live-collected form into a submission plan. Pure given the DOM
    read, so it is unit-tested without a browser."""
    if not collected:
        return {"refuse": "form not found on the page", "fills": [],
                "skipped": [], "submitted_once": False}
    email = test_email or default_test_email(site_url)
    return plan_submission(collected.get("fields") or [],
                           collected.get("iframes") or [], email,
                           form_visible=collected.get("form_visible", True))


def submit_test_form(url: str, form_selector: str, *, test_email: str = None,
                     settle_ms: int = 2500) -> dict:
    """Fill and submit ONE form ONCE, and report what happened.

    Refuses (without submitting) if the plan refuses — e.g. a payment form.
    Returns a structured record: the plan, whether it submitted, the resulting
    status/URL, thank-you detection, and any tracking event that fired.
    """
    from playwright.sync_api import sync_playwright

    guard = SubmitGuard()
    record = {"submitted": False, "refused": None, "plan": None,
              "final_url": None, "status": None, "thank_you": False,
              "events": [], "error": None}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1200)

            collected = page.evaluate(_COLLECT_ONE_FORM_JS, form_selector)
            plan = build_plan_for_live_form(collected, url, test_email)
            record["plan"] = plan
            if plan["refuse"]:
                record["refused"] = plan["refuse"]
                return record

            # Observe conversion events fired by the form's own handler.
            page.evaluate(TRACKING_OBSERVER_JS)

            # Fill only what the plan says, by name/id, in the target form only.
            for fill in plan["fills"]:
                _fill_one(page, form_selector, fill)

            status_holder = {"status": None}
            def _on_response(resp):
                try:
                    if resp.request.method.upper() == "POST":
                        status_holder["status"] = resp.status
                except Exception:
                    pass
            page.on("response", _on_response)

            before_url = page.url
            submit = page.query_selector(
                f"{form_selector} button[type=submit], {form_selector} input[type=submit], "
                f"{form_selector} button:not([type])")
            if submit is None:
                record["error"] = "no submit control found"
                return record

            # THE ONE submission. SubmitGuard makes a second fire impossible.
            guard.fire(lambda: submit.click(timeout=5000, no_wait_after=True))
            record["submitted"] = True
            page.wait_for_timeout(settle_ms)

            record["final_url"] = page.url
            record["status"] = status_holder["status"]
            try:
                body_text = page.inner_text("body")[:5000]
            except Exception:
                body_text = ""
            record["thank_you"] = _thankyou_detected(before_url, page.url, body_text)
            try:
                record["events"] = page.evaluate("window.__linkspy_events || []")
            except Exception:
                record["events"] = []
            return record
        except Exception as e:
            record["error"] = f"{type(e).__name__}: {e}"
            return record
        finally:
            browser.close()


def _fill_one(page, form_selector: str, fill: dict) -> None:
    name, value = fill.get("name"), fill.get("value")
    if not name:
        return
    for sel in (f'{form_selector} [name="{name}"]', f'{form_selector} #{name}'):
        try:
            el = page.query_selector(sel)
            if el is not None:
                el.fill(value, timeout=3000)
                return
        except Exception:
            continue
