"use client";

import { motion } from "framer-motion";
import { AlertOctagon, Ghost, HelpCircle } from "lucide-react";
import { Bucket, LinkResult } from "@/types";
import { inBucket } from "@/lib/buckets";
import FixPanel from "./FixPanel";

interface IssueSectionsProps {
  results: LinkResult[];
  /** Findings can only be addressed once the scan has been saved. */
  siteId?: string | null;
}

interface SectionSpec {
  bucket: Bucket;
  title: string;
  color: string;
  bg: string;
  border: string;
  icon: typeof Ghost;
  blurb: string;
  showConfidence: boolean;
}

// Broken is urgent/red, dead CTAs are actionable/orange, unverifiable is a
// neutral soft warning — never presented as a defect.
const SECTIONS: SectionSpec[] = [
  {
    bucket: "broken",
    title: "Broken Links",
    color: "#e05c5c",
    bg: "rgba(224,92,92,0.08)",
    border: "rgba(224,92,92,0.28)",
    icon: AlertOctagon,
    blurb: "These fail outright. Fix first.",
    showConfidence: false,
  },
  {
    bucket: "dead_cta",
    title: "Dead CTAs",
    color: "#f5a623",
    bg: "rgba(245,166,35,0.08)",
    border: "rgba(245,166,35,0.28)",
    icon: Ghost,
    blurb: "Buttons and links styled as calls-to-action that lead nowhere useful.",
    showConfidence: true,
  },
  {
    bucket: "unverifiable",
    title: "Unverifiable",
    color: "#f5a623",
    bg: "rgba(245,166,35,0.06)",
    border: "rgba(245,166,35,0.20)",
    icon: HelpCircle,
    blurb: "Couldn't verify automatically — please check manually",
    showConfidence: false,
  },
];

export default function IssueSections({ results, siteId }: IssueSectionsProps) {
  const sections = SECTIONS.map((spec) => ({
    spec,
    items: inBucket(results, spec.bucket),
  })).filter((s) => s.items.length > 0);

  if (sections.length === 0) return null;

  return (
    <div className="w-full max-w-5xl mx-auto mt-8 px-4 space-y-6">
      {sections.map(({ spec, items }) => (
        <Section key={spec.bucket} spec={spec} items={items} siteId={siteId} />
      ))}
    </div>
  );
}

function Section({ spec, items, siteId }: { spec: SectionSpec; items: LinkResult[]; siteId?: string | null }) {
  const Icon = spec.icon;

  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="glass-card overflow-hidden"
      style={{ background: spec.bg, border: `1px solid ${spec.border}` }}
    >
      <header className="px-5 py-4 flex items-start gap-3">
        <Icon size={20} style={{ color: spec.color }} className="mt-0.5 shrink-0" />
        <div>
          <h3 className="text-base font-semibold" style={{ color: spec.color }}>
            {spec.title}
            <span className="ml-2 text-sm font-normal opacity-70">({items.length})</span>
          </h3>
          <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
            {spec.blurb}
          </p>
        </div>
      </header>

      <ul className="divide-y" style={{ borderColor: "var(--border-subtle)" }}>
        {items.map((r, i) => (
          <IssueRow key={`${r.url}-${r.anchor_text}-${i}`} result={r} spec={spec} siteId={siteId} />
        ))}
      </ul>
    </motion.section>
  );
}

function IssueRow({ result, spec, siteId }: { result: LinkResult; spec: SectionSpec; siteId?: string | null }) {
  const label = result.anchor_text?.trim() || "[no text]";
  // A dead CTA has no destination — showing its page URL as a link is noise.
  const showUrl = spec.bucket !== "dead_cta" && result.url;

  return (
    <li
      className="px-5 py-3 flex flex-wrap items-start gap-x-3 gap-y-1.5 scroll-mt-24"
      data-finding-row
      data-finding-url={result.url}
      data-finding-anchor={result.anchor_text ?? ""}
      data-finding-reason={result.reason ?? result.error ?? ""}
      data-finding-bucket={spec.bucket}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>{label}</span>

          {spec.showConfidence && result.confidence && result.confidence !== "low" && (
            <ConfidenceChip confidence={result.confidence} />
          )}

          {result.status_code != null && (
            <span
              className="text-[11px] tabular-nums rounded px-1.5 py-0.5"
              style={{ background: "rgba(28,28,46,0.06)", color: "var(--text-secondary)" }}
            >
              {result.status_code}
            </span>
          )}

          {/* A link in several zones is one row — say so, or it reads as missing. */}
          {(result.occurrences ?? 1) > 1 && (
            <span
              className="text-[11px] tabular-nums rounded px-1.5 py-0.5"
              style={{ background: "rgba(28,28,46,0.04)", color: "var(--text-muted)" }}
              title={`Linked ${result.occurrences} times on this page`}
            >
              ×{result.occurrences}
            </span>
          )}

          {result.zones && result.zones.length > 0 && (
            <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
              {result.zones.join(" · ")}
            </span>
          )}
        </div>

        {/* Every item displays its reason. */}
        {result.reason && (
          <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
            {result.reason}
          </p>
        )}
        {!result.reason && result.error && (
          <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
            {result.error}
          </p>
        )}

        {showUrl && (
          <a
            href={result.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs mt-1 block truncate hover:underline"
            style={{ color: "#7a7a8c" }}
          >
            {result.url}
          </a>
        )}

        {/* Unverifiable items are not defects, so they get no fix workflow. */}
        {spec.bucket !== "unverifiable" && (
          <FixPanel result={result} findingId={result.fingerprint} siteId={siteId} />
        )}
      </div>
    </li>
  );
}

function ConfidenceChip({ confidence }: { confidence: "high" | "medium" }) {
  const styles = {
    high: { bg: "rgba(224,92,92,0.15)", fg: "#e05c5c" },
    medium: { bg: "rgba(245,166,35,0.15)", fg: "#f5a623" },
  }[confidence];

  return (
    <span
      className="text-[10px] uppercase tracking-wider rounded-full px-2 py-0.5 font-medium"
      style={{ background: styles.bg, color: styles.fg }}
    >
      {confidence}
    </span>
  );
}
