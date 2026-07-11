"use client";

import NavBar from "@/components/NavBar";
import SelfHealPanel from "@/components/SelfHealPanel";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

export default function SelfHealPage() {
  return (
    <main className="min-h-screen">
      <NavBar />
      <div className="ds-container" style={{ maxWidth: 760, padding: "112px 16px 64px" }}>
        <Link
          href="/"
          className="ds-text-muted"
          style={{ display: "inline-flex", alignItems: "center", gap: 8, marginBottom: 24, fontSize: "var(--text-body)", textDecoration: "none" }}
        >
          <ArrowLeft size={15} /> Back to scanner
        </Link>

        <h1
          className="ds-text-primary"
          style={{ fontWeight: 700, fontSize: "var(--text-display)", letterSpacing: "-0.5px", marginBottom: 8 }}
        >
          Self-heal
        </h1>
        {/* The single, two-sentence description. */}
        <p className="ds-text-secondary" style={{ fontSize: "var(--text-body)", lineHeight: "var(--leading-normal)", marginBottom: 28, maxWidth: 560 }}>
          Self-heal scans a page and, for the broken links it can prove a fix for,
          opens a pull request on an approved repository. It never merges — you
          review every change before it ships.
        </p>

        <SelfHealPanel />
      </div>
    </main>
  );
}
