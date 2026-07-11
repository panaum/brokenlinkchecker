"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, ShieldCheck } from "lucide-react";
import { setPortalToken } from "@/lib/backendClient";

// The client's login: consume the invite token, store the portal session token,
// go to the portal. The invite link IS the credential — no password, no Google.
export default function PortalAcceptPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("token");
    if (!token) { setError("This link is missing its invite token."); return; }
    (async () => {
      try {
        const res = await fetch(`/api/invites/${token}/accept`, { method: "POST" });
        const body = await res.json();
        if (!res.ok || !body.token) {
          setError(body.error || "This invite link is invalid or has expired.");
          return;
        }
        setPortalToken(body.token);
        router.replace("/portal");
      } catch {
        setError("Couldn't reach the server. Please try the link again.");
      }
    })();
  }, [router]);

  return (
    <main style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: 24, background: "var(--surface-page)" }}>
      <div className="ds-card ds-card-pad" style={{ maxWidth: 400, textAlign: "center" }}>
        {error ? (
          <>
            <div className="font-display ds-text-primary" style={{ fontSize: "var(--text-heading)", fontWeight: 700, marginBottom: 8 }}>
              This link didn&apos;t work
            </div>
            <p className="ds-text-secondary" style={{ fontSize: "var(--text-body)" }}>{error}</p>
            <p className="ds-text-muted" style={{ fontSize: "var(--text-caption)", marginTop: 12 }}>
              Ask your Apexure contact to send a fresh invite link.
            </p>
          </>
        ) : (
          <>
            <ShieldCheck size={28} style={{ color: "var(--signal)", marginBottom: 12 }} />
            <div className="ds-text-primary" style={{ fontSize: "var(--text-body)", display: "inline-flex", alignItems: "center", gap: 8 }}>
              <Loader2 size={15} className="animate-spin" /> Signing you in…
            </div>
          </>
        )}
      </div>
    </main>
  );
}
