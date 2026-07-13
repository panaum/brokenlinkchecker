"use client";

import { use, useEffect, useState } from "react";
import { Printer, Loader2 } from "lucide-react";
import AttestationDoc, { AttestationDocData } from "@/components/AttestationDoc";
import { staffToken, getPortalToken } from "@/lib/backendClient";

interface Row { id: string; document: AttestationDocData; content_hash: string; agency_name?: string; issued_at?: string; }

export default function AttestationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [row, setRow] = useState<Row | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { (async () => {
    try {
      const token = (await staffToken()) || getPortalToken() || "";
      const res = await fetch(`/api/attestations/${id}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || `Could not load this attestation (HTTP ${res.status}).`);
      setRow(await res.json());
    } catch (e) { setErr(e instanceof Error ? e.message : "Failed to load."); }
  })(); }, [id]);

  if (err) return <Centered msg={err} />;
  if (!row) return <Centered spinner />;
  return (
    <div style={{ position: "relative" }}>
      <button onClick={() => window.print()} className="report-print-btn"
        style={{ position: "fixed", top: 20, right: 20, zIndex: 20, display: "inline-flex", alignItems: "center", gap: 8, background: "#7c3aed", color: "#fff", border: "none", borderRadius: 10, padding: "10px 16px", fontSize: 14, fontWeight: 600, cursor: "pointer", boxShadow: "0 4px 14px rgba(124,58,237,0.35)" }}>
        <Printer size={16} /> Save as PDF
      </button>
      <AttestationDoc doc={row.document} contentHash={row.content_hash} agency={row.agency_name} issuedAt={row.issued_at} />
    </div>
  );
}

function Centered({ msg, spinner }: { msg?: string; spinner?: boolean }) {
  return <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#f4f3f9", color: "#55506b" }}>
    {spinner ? <Loader2 size={28} className="animate-spin" /> : <div style={{ textAlign: "center" }}><div style={{ fontFamily: "var(--font-stack-display)", fontSize: 22, color: "#1c1a2e", marginBottom: 8 }}>Attestation unavailable</div><div>{msg}</div></div>}
  </div>;
}
