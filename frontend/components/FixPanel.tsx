"use client";

import { useCallback, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, Copy, Loader2, RefreshCw, Wrench } from "lucide-react";
import { LinkResult } from "@/types";

interface FixSuggestion {
  issue_type: string;
  fix_type: string;
  proposed_value: string | null;
  title: string;
  steps: string[];
  est_time_minutes: number;
  requires_dev: boolean;
  confidence: string;
  builder: string;
  template_source: string;
}

interface VerifyOutcome {
  verified: boolean;
  status: string;
  checked: boolean;
  reason: string;
}

interface FixPanelProps {
  result: LinkResult;
  /** The scan gives us a fingerprint, not a database id. The backend resolves
   *  it against the site — a fingerprint is scoped to a page, not to a site. */
  findingId?: string;
  siteId?: string | null;
}

/**
 * Per-finding actions: read the hand-written fix, re-check it live, or copy a
 * message for the client.
 *
 * `findingId` only exists once a scan has been persisted. Without it these
 * actions have nothing to address, so the panel says so rather than rendering
 * buttons that quietly fail.
 */
export default function FixPanel({ result, findingId, siteId }: FixPanelProps) {
  const [fix, setFix] = useState<FixSuggestion | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [verify, setVerify] = useState<VerifyOutcome | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scope = siteId ? `?site_id=${encodeURIComponent(siteId)}` : "";

  const loadFix = useCallback(async () => {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (fix || !findingId) return;

    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/findings/${findingId}/fix${scope}`);
      if (!res.ok) throw new Error(`Could not load the fix (${res.status})`);
      setFix((await res.json()) as FixSuggestion);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the fix");
    } finally {
      setLoading(false);
    }
  }, [open, fix, findingId, scope]);

  const recheck = useCallback(async () => {
    if (!findingId) return;
    setVerifying(true);
    setError(null);
    try {
      const res = await fetch(`/api/findings/${findingId}/verify${scope}`, { method: "POST" });
      setVerify((await res.json()) as VerifyOutcome);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Re-check failed");
    } finally {
      setVerifying(false);
    }
  }, [findingId, scope]);

  const copyClientMessage = useCallback(async () => {
    if (!findingId) return;
    try {
      const res = await fetch(`/api/findings/${findingId}/client-message${scope}`);
      const body = (await res.json()) as { subject: string; body: string };
      await navigator.clipboard.writeText(`Subject: ${body.subject}\n\n${body.body}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Could not copy the client message");
    }
  }, [findingId, scope]);

  if (!findingId || !siteId) {
    return (
      <p className="text-[11px] mt-2" style={{ color: "rgba(255,255,255,0.35)" }}>
        Fix guidance appears once this scan has been saved.
      </p>
    );
  }

  return (
    <div className="mt-2">
      <div className="flex flex-wrap items-center gap-2">
        <Action onClick={loadFix} icon={Wrench} label={open ? "Hide fix" : "How to fix"} triage="fix" />
        <Action
          onClick={recheck}
          icon={verifying ? Loader2 : RefreshCw}
          label={verifying ? "Re-checking…" : "Re-check"}
          spin={verifying}
          triage="recheck"
        />
        <Action
          onClick={copyClientMessage}
          icon={copied ? Check : Copy}
          label={copied ? "Copied" : "Copy client message"}
          triage="copy"
        />
      </div>

      {verify && (
        <p
          className="text-[11px] mt-2"
          style={{ color: verify.verified ? "#4ade80" : "rgba(255,255,255,0.55)" }}
        >
          {verify.verified ? "✓ Verified fixed — " : ""}
          {verify.reason}
        </p>
      )}

      {error && (
        <p className="text-[11px] mt-2" style={{ color: "#f87171" }}>
          {error}
        </p>
      )}

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div
              className="mt-3 rounded-lg p-4 text-xs"
              style={{ background: "rgba(255,255,255,0.04)" }}
            >
              {loading && <span style={{ color: "rgba(255,255,255,0.5)" }}>Loading…</span>}

              {fix && (
                <>
                  <div className="flex flex-wrap items-center gap-2 mb-2">
                    <span className="font-semibold text-white/90">{fix.title}</span>
                    <Chip>{fix.est_time_minutes} min</Chip>
                    {fix.requires_dev && <Chip>needs a developer</Chip>}
                    <Chip>{fix.builder}</Chip>
                  </div>

                  {fix.proposed_value ? (
                    <p className="mb-2" style={{ color: "rgba(255,255,255,0.65)" }}>
                      Suggested replacement:{" "}
                      <code className="font-mono text-[11px]">{fix.proposed_value}</code>{" "}
                      <span style={{ color: "rgba(255,255,255,0.4)" }}>
                        (confidence: {fix.confidence} — confirm before applying)
                      </span>
                    </p>
                  ) : (
                    <p className="mb-2" style={{ color: "rgba(255,255,255,0.4)" }}>
                      No replacement suggested — this one needs a human decision.
                    </p>
                  )}

                  <ol className="list-decimal ml-4 space-y-1.5" style={{ color: "rgba(255,255,255,0.7)" }}>
                    {fix.steps.map((step, i) => (
                      <li key={i}>{step}</li>
                    ))}
                  </ol>

                  <p className="mt-3 text-[10px]" style={{ color: "rgba(255,255,255,0.3)" }}>
                    Written by hand for {fix.builder} · {fix.template_source}
                  </p>
                </>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span
      className="text-[10px] rounded-full px-2 py-0.5"
      style={{ background: "rgba(255,255,255,0.08)", color: "rgba(255,255,255,0.6)" }}
    >
      {children}
    </span>
  );
}

function Action({
  onClick,
  icon: Icon,
  label,
  spin,
  triage,
}: {
  onClick: () => void;
  icon: typeof Wrench;
  label: string;
  spin?: boolean;
  triage?: string;
}) {
  return (
    <button
      onClick={onClick}
      data-triage={triage}
      className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[11px] transition-colors cursor-pointer"
      style={{ background: "rgba(255,255,255,0.06)", color: "rgba(255,255,255,0.7)" }}
    >
      <Icon size={12} className={spin ? "animate-spin" : ""} />
      {label}
    </button>
  );
}
