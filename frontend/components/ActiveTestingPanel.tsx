"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Loader2, AlertTriangle, FlaskConical, Ban } from "lucide-react";

interface OptinForm {
  form_key: string;
  test_email?: string | null;
  enabled: boolean;
}

interface OptinData {
  global_enabled?: boolean;
  forms?: OptinForm[];
  error?: string;
}

// qa+linkspy@<domain> — the filterable default the client can route to trash.
function defaultTestEmail(siteUrl: string): string {
  try {
    const host = new URL(siteUrl).hostname.replace(/^www\./, "");
    return `qa+linkspy@${host}`;
  } catch {
    return "qa+linkspy@example.com";
  }
}

export default function ActiveTestingPanel({ siteId, siteUrl }: { siteId: string; siteUrl: string }) {
  const [data, setData] = useState<OptinData | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  // Enable-a-form form state
  const [selector, setSelector] = useState("");
  const [email, setEmail] = useState(defaultTestEmail(siteUrl));
  const [confirmed, setConfirmed] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`/api/sites/${siteId}/forms/optin`, { cache: "no-store" });
      setData(await res.json());
    } catch {
      setData({ error: "Could not load active-testing settings." });
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    load();
  }, [load]);

  const setOptin = async (formKey: string, enabled: boolean, testEmail?: string) => {
    setBusy(formKey);
    setResult(null);
    try {
      await fetch(`/api/sites/${siteId}/forms/optin`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ form_key: formKey, enabled, test_email: testEmail }),
      });
      await load();
    } finally {
      setBusy(null);
    }
  };

  const enableForm = async () => {
    if (!selector.trim() || !confirmed) return;
    await setOptin(selector.trim(), true, email.trim());
    setSelector("");
    setConfirmed(false);
  };

  const runTest = async (form: OptinForm) => {
    setBusy(form.form_key);
    setResult(null);
    try {
      const res = await fetch(`/api/sites/${siteId}/forms/active-test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ form_key: form.form_key, form_selector: form.form_key }),
      });
      const body = await res.json();
      if (body.refused || body.error) {
        setResult(body.error || "Refused.");
      } else if (body.refused_reason || body.plan?.refuse) {
        setResult(`Refused: ${body.plan?.refuse ?? body.refused_reason}`);
      } else if (body.submitted) {
        const bits = [`Submitted once`];
        if (body.status) bits.push(`server responded ${body.status}`);
        bits.push(body.thank_you ? "thank-you page shown" : "no thank-you page detected");
        bits.push(
          body.events && body.events.length > 0
            ? `conversion event fired (${body.events.length})`
            : "no conversion event fired",
        );
        setResult(bits.join(" · "));
      } else if (body.refused) {
        setResult(body.refused);
      } else {
        setResult(body.error || "Did not submit.");
      }
      await load();
    } finally {
      setBusy(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm" style={{ color: "rgba(255,255,255,0.4)" }}>
        <Loader2 size={14} className="animate-spin" /> Loading active testing…
      </div>
    );
  }

  const globalOn = Boolean(data?.global_enabled);
  const forms = data?.forms ?? [];

  return (
    <div
      className="rounded-xl p-4"
      style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(251,146,60,0.25)" }}
    >
      <div className="flex items-center gap-2 mb-2" style={{ fontWeight: 600, fontSize: 14 }}>
        <FlaskConical size={16} style={{ color: "#fb923c" }} />
        Active form testing
        <span
          style={{
            marginLeft: 6, fontSize: 10, padding: "1px 7px", borderRadius: 999,
            background: globalOn ? "rgba(251,146,60,0.15)" : "rgba(255,255,255,0.06)",
            color: globalOn ? "#fdba74" : "rgba(255,255,255,0.5)",
          }}
        >
          {globalOn ? "enabled globally" : "off globally"}
        </span>
      </div>

      {/* The mandatory warning — shown always, not just at enable time. */}
      <div
        className="flex gap-2 rounded-lg px-3 py-2 mb-3"
        style={{ background: "rgba(251,146,60,0.08)", border: "1px solid rgba(251,146,60,0.2)" }}
      >
        <AlertTriangle size={14} style={{ color: "#fb923c", flexShrink: 0, marginTop: 2 }} />
        <p style={{ fontSize: 12, color: "rgba(255,255,255,0.7)", lineHeight: 1.5, margin: 0 }}>
          This submits the form for real. Configure your CRM to filter the test
          address <strong style={{ color: "#fdba74" }}>{email}</strong> before you
          run a test. Payment forms are always refused.
        </p>
      </div>

      {!globalOn && (
        <p style={{ fontSize: 12, color: "rgba(255,255,255,0.5)", marginBottom: 10 }}>
          Turned off globally. A test will refuse until <code>ACTIVE_FORM_TESTING</code>{" "}
          is set on the server. You can still enable individual forms below so
          they are ready.
        </p>
      )}

      {/* Enabled forms */}
      {forms.length > 0 && (
        <div className="flex flex-col gap-2 mb-3">
          {forms.map((f) => (
            <div
              key={f.form_key}
              className="flex items-center justify-between rounded-lg px-3 py-2"
              style={{ background: "rgba(255,255,255,0.03)", fontSize: 12 }}
            >
              <div className="min-w-0">
                <div style={{ color: "rgba(255,255,255,0.85)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {f.form_key}
                </div>
                <div style={{ color: "rgba(255,255,255,0.4)" }}>
                  {f.enabled ? `enabled · ${f.test_email ?? email}` : "disabled"}
                </div>
              </div>
              <div className="flex items-center gap-2" style={{ flexShrink: 0 }}>
                {f.enabled && globalOn && (
                  <button
                    onClick={() => runTest(f)}
                    disabled={busy === f.form_key}
                    className="cursor-pointer"
                    style={{ padding: "3px 10px", borderRadius: 6, fontSize: 11, fontWeight: 500,
                             border: "1px solid rgba(251,146,60,0.4)", background: "rgba(251,146,60,0.12)", color: "#fdba74" }}
                  >
                    {busy === f.form_key ? "Testing…" : "Run test"}
                  </button>
                )}
                <button
                  onClick={() => setOptin(f.form_key, !f.enabled)}
                  disabled={busy === f.form_key}
                  className="cursor-pointer"
                  style={{ padding: "3px 10px", borderRadius: 6, fontSize: 11,
                           border: "1px solid rgba(255,255,255,0.15)", color: "rgba(255,255,255,0.6)" }}
                >
                  {f.enabled ? "Disable" : "Enable"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {result && (
        <p style={{ fontSize: 12, color: "rgba(255,255,255,0.7)", marginBottom: 10, lineHeight: 1.5 }}>
          {result}
        </p>
      )}

      {/* Enable a form — deliberate, with an explicit confirmation. */}
      <div className="flex flex-col gap-2 pt-2" style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
        <div style={{ fontSize: 11, color: "rgba(255,255,255,0.4)" }}>Enable a form for testing</div>
        <input
          value={selector}
          onChange={(e) => setSelector(e.target.value)}
          placeholder="form CSS selector, e.g. #contact-form"
          className="rounded-lg px-3 py-2 text-sm outline-none"
          style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", color: "#fff" }}
        />
        <input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="rounded-lg px-3 py-2 text-sm outline-none"
          style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", color: "#fff" }}
        />
        <label className="flex items-center gap-2" style={{ fontSize: 12, color: "rgba(255,255,255,0.6)" }}>
          <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
          I have set my CRM to filter {email}, and I understand this sends a real submission.
        </label>
        <button
          onClick={enableForm}
          disabled={!selector.trim() || !confirmed || busy !== null}
          className="cursor-pointer"
          style={{
            padding: "6px 12px", borderRadius: 8, fontSize: 12, fontWeight: 500,
            border: "1px solid rgba(251,146,60,0.4)",
            background: !selector.trim() || !confirmed ? "rgba(255,255,255,0.04)" : "rgba(251,146,60,0.15)",
            color: !selector.trim() || !confirmed ? "rgba(255,255,255,0.3)" : "#fdba74",
          }}
        >
          Enable this form
        </button>
      </div>
    </div>
  );
}
