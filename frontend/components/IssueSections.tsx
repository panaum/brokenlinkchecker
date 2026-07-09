"use client";

import { motion } from "framer-motion";
import { AlertOctagon, Ghost, HelpCircle } from "lucide-react";
import { Bucket, LinkResult } from "@/types";
import { inBucket } from "@/lib/buckets";

interface IssueSectionsProps {
  results: LinkResult[];
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
    color: "#f87171",
    bg: "rgba(248,113,113,0.08)",
    border: "rgba(248,113,113,0.28)",
    icon: AlertOctagon,
    blurb: "These fail outright. Fix first.",
    showConfidence: false,
  },
  {
    bucket: "dead_cta",
    title: "Dead CTAs",
    color: "#fb923c",
    bg: "rgba(251,146,60,0.08)",
    border: "rgba(251,146,60,0.28)",
    icon: Ghost,
    blurb: "Buttons and links styled as calls-to-action that lead nowhere useful.",
    showConfidence: true,
  },
  {
    bucket: "unverifiable",
    title: "Unverifiable",
    color: "#fbbf24",
    bg: "rgba(251,191,36,0.06)",
    border: "rgba(251,191,36,0.20)",
    icon: HelpCircle,
    blurb: "Couldn't verify automatically — please check manually",
    showConfidence: false,
  },
];

export default function IssueSections({ results }: IssueSectionsProps) {
  const sections = SECTIONS.map((spec) => ({
    spec,
    items: inBucket(results, spec.bucket),
  })).filter((s) => s.items.length > 0);

  if (sections.length === 0) return null;

  return (
    <div className="w-full max-w-5xl mx-auto mt-8 px-4 space-y-6">
      {sections.map(({ spec, items }) => (
        <Section key={spec.bucket} spec={spec} items={items} />
      ))}
    </div>
  );
}

function Section({ spec, items }: { spec: SectionSpec; items: LinkResult[] }) {
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
          <p className="text-xs mt-0.5" style={{ color: "rgba(255,255,255,0.55)" }}>
            {spec.blurb}
          </p>
        </div>
      </header>

      <ul className="divide-y" style={{ borderColor: "rgba(255,255,255,0.06)" }}>
        {items.map((r, i) => (
          <IssueRow key={`${r.url}-${r.anchor_text}-${i}`} result={r} spec={spec} />
        ))}
      </ul>
    </motion.section>
  );
}

function IssueRow({ result, spec }: { result: LinkResult; spec: SectionSpec }) {
  const label = result.anchor_text?.trim() || "[no text]";
  // A dead CTA has no destination — showing its page URL as a link is noise.
  const showUrl = spec.bucket !== "dead_cta" && result.url;

  return (
    <li className="px-5 py-3 flex flex-wrap items-start gap-x-3 gap-y-1.5">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-white/90 truncate">{label}</span>

          {spec.showConfidence && result.confidence && result.confidence !== "low" && (
            <ConfidenceChip confidence={result.confidence} />
          )}

          {result.status_code != null && (
            <span
              className="text-[11px] tabular-nums rounded px-1.5 py-0.5"
              style={{ background: "rgba(255,255,255,0.08)", color: "rgba(255,255,255,0.65)" }}
            >
              {result.status_code}
            </span>
          )}

          {/* A link in several zones is one row — say so, or it reads as missing. */}
          {(result.occurrences ?? 1) > 1 && (
            <span
              className="text-[11px] tabular-nums rounded px-1.5 py-0.5"
              style={{ background: "rgba(255,255,255,0.06)", color: "rgba(255,255,255,0.55)" }}
              title={`Linked ${result.occurrences} times on this page`}
            >
              ×{result.occurrences}
            </span>
          )}

          {result.zones && result.zones.length > 0 && (
            <span className="text-[11px]" style={{ color: "rgba(255,255,255,0.4)" }}>
              {result.zones.join(" · ")}
            </span>
          )}
        </div>

        {/* Every item displays its reason. */}
        {result.reason && (
          <p className="text-xs mt-1" style={{ color: "rgba(255,255,255,0.55)" }}>
            {result.reason}
          </p>
        )}
        {!result.reason && result.error && (
          <p className="text-xs mt-1" style={{ color: "rgba(255,255,255,0.55)" }}>
            {result.error}
          </p>
        )}

        {showUrl && (
          <a
            href={result.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs mt-1 block truncate hover:underline"
            style={{ color: "rgba(147,197,253,0.85)" }}
          >
            {result.url}
          </a>
        )}
      </div>
    </li>
  );
}

function ConfidenceChip({ confidence }: { confidence: "high" | "medium" }) {
  const styles = {
    high: { bg: "rgba(248,113,113,0.15)", fg: "#fca5a5" },
    medium: { bg: "rgba(251,191,36,0.15)", fg: "#fcd34d" },
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
