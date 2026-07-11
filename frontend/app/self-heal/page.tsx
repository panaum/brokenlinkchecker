"use client";

import NavBar from "@/components/NavBar";
import SelfHealPanel from "@/components/SelfHealPanel";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

export default function SelfHealPage() {
  return (
    <main className="min-h-screen">
      <NavBar />
      <div className="max-w-3xl mx-auto px-4 pt-28 pb-16">
        <Link
          href="/"
          className="inline-flex items-center gap-2 mb-6"
          style={{ color: "rgba(255,255,255,0.5)", fontSize: 14, textDecoration: "none" }}
        >
          <ArrowLeft size={15} /> Back to scanner
        </Link>

        <h1
          className="mb-2"
          style={{
            fontFamily: "var(--font-poppins), Poppins, sans-serif",
            fontWeight: 700,
            fontSize: 34,
            letterSpacing: "-0.5px",
          }}
        >
          Self-heal
        </h1>
        <p style={{ color: "rgba(255,255,255,0.55)", fontSize: 16, marginBottom: 28, lineHeight: 1.6 }}>
          Scan a page and, for the broken links it can <strong>prove</strong> a fix
          for, open a pull request automatically. It never merges, and only ever
          touches a repository an operator has allowlisted.
        </p>

        <SelfHealPanel />
      </div>
    </main>
  );
}
