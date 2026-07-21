"use client";

import { use, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Printer, Loader2 } from "lucide-react";
import VigilanceReport, { ReportData } from "@/components/VigilanceReport";
import { staffToken, getPortalToken } from "@/lib/backendClient";

interface Report { id: string; site_id: string; period_label: string; data_json: ReportData; site_name?: string; }

export default function ReportPage({ params }: { params: Promise<{ report_id: string }> }) {
  const { report_id } = use(params);
  const wantsPrint = useSearchParams().get("print") === "1";
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const token = (await staffToken()) || getPortalToken() || "";
        const res = await fetch(`/api/reports/${report_id}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) {
          const j = await res.json().catch(() => ({}));
          throw new Error(j.error || `Could not load this report (HTTP ${res.status}).`);
        }
        setReport(await res.json());
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load report.");
      }
    })();
  }, [report_id]);

  // Opened from the shelf's "PDF" action — trigger the print dialog once painted.
  useEffect(() => {
    if (report && wantsPrint) {
      const t = setTimeout(() => window.print(), 400);
      return () => clearTimeout(t);
    }
  }, [report, wantsPrint]);

  if (error) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#f4f3f9", color: "#55506b", fontFamily: "var(--font-stack-body)" }}>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 22, color: "#1c1a2e", marginBottom: 8 }}>Report unavailable</div>
          <div>{error}</div>
        </div>
      </div>
    );
  }

  if (!report) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#f4f3f9", color: "#928da6" }}>
        <Loader2 size={28} className="animate-spin" />
      </div>
    );
  }

  const name = report.site_name || "Your site";
  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={() => window.print()}
        className="report-print-btn"
        style={{
          position: "fixed", top: 20, right: 20, zIndex: 20, display: "inline-flex", alignItems: "center", gap: 8,
          background: "#4f46e5", color: "#fff", border: "none", borderRadius: 10, padding: "10px 16px",
          fontSize: 14, fontWeight: 600, cursor: "pointer", boxShadow: "0 6px 20px rgba(79,70,229,0.25)",
        }}
      >
        <Printer size={16} /> Save as PDF
      </button>
      <VigilanceReport data={report.data_json} siteName={name} />
    </div>
  );
}
