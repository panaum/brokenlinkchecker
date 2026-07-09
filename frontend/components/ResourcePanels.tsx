"use client";

import { motion } from "framer-motion";
import { HostCount, ResourceType } from "@/types";

interface ResourcePanelsProps {
  linkTypes?: Partial<Record<ResourceType, number>>;
  topHosts?: HostCount[];
  schemes?: Record<string, number>;
}

// Display order matches how much a failure of that type hurts.
const TYPE_ORDER: ResourceType[] = [
  "anchor",
  "script",
  "stylesheet",
  "image",
  "css_url",
  "iframe",
  "media",
  "meta_image",
  "favicon",
  "other",
];

const TYPE_LABELS: Record<ResourceType, string> = {
  anchor: "<a href>",
  script: "<script src>",
  stylesheet: "<link stylesheet>",
  image: "<img src>",
  css_url: "CSS url()",
  iframe: "iframe",
  media: "media",
  meta_image: "social/meta image",
  favicon: "favicon",
  other: "other",
};

const SCHEME_LABELS: Record<string, string> = {
  https: "https",
  http: "http",
  mailto: "mailto",
  tel: "tel",
  data: "data",
};

export default function ResourcePanels({
  linkTypes,
  topHosts,
  schemes,
}: ResourcePanelsProps) {
  const typeRows = TYPE_ORDER.filter((t) => (linkTypes?.[t] ?? 0) > 0).map((t) => ({
    label: TYPE_LABELS[t],
    count: linkTypes![t]!,
  }));

  const schemeRows = Object.entries(schemes ?? {})
    .filter(([, count]) => count > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([scheme, count]) => ({
      label: SCHEME_LABELS[scheme] ?? scheme,
      count,
    }));

  const hostRows = (topHosts ?? []).map((h) => ({ label: h.host, count: h.count }));

  if (!typeRows.length && !schemeRows.length && !hostRows.length) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="w-full max-w-5xl mx-auto mt-8 px-4 grid gap-4 md:grid-cols-3"
    >
      <Panel title="Link Types" rows={typeRows} mono />
      <Panel title="Top Hosts" rows={hostRows} mono />
      <Panel title="Link Schemes" rows={schemeRows} mono />
    </motion.div>
  );
}

function Panel({
  title,
  rows,
  mono,
}: {
  title: string;
  rows: { label: string; count: number }[];
  mono?: boolean;
}) {
  if (!rows.length) return null;
  const max = Math.max(...rows.map((r) => r.count), 1);

  return (
    <section className="glass-card p-5">
      <h3
        className="text-[11px] uppercase tracking-widest mb-3"
        style={{ color: "rgba(255,255,255,0.5)" }}
      >
        {title}
      </h3>
      <ul className="space-y-2">
        {rows.map((row) => (
          <li key={row.label} className="text-xs">
            <div className="flex items-center justify-between gap-3">
              <span
                className={`truncate ${mono ? "font-mono" : ""}`}
                style={{ color: "rgba(255,255,255,0.75)" }}
                title={row.label}
              >
                {row.label}
              </span>
              <span
                className="tabular-nums shrink-0"
                style={{ color: "rgba(255,255,255,0.9)" }}
              >
                {row.count}
              </span>
            </div>
            <div
              className="mt-1 h-1 rounded-full overflow-hidden"
              style={{ background: "rgba(255,255,255,0.06)" }}
            >
              <div
                className="h-full rounded-full"
                style={{
                  width: `${(row.count / max) * 100}%`,
                  background: "rgba(147,197,253,0.55)",
                }}
              />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
