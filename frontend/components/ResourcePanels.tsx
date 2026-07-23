"use client";

import { motion } from "framer-motion";
import { HostCount, RedirectFlag, RedirectSummary, ResourceType } from "@/types";

interface ResourcePanelsProps {
  linkTypes?: Partial<Record<ResourceType, number>>;
  topHosts?: HostCount[];
  schemes?: Record<string, number>;
  redirects?: RedirectSummary | null;
}

const FLAG_LABELS: Record<RedirectFlag, string> = {
  long_chain: "Long chains (3+ hops)",
  http_to_https: "http → https hops",
  slash_bounce: "Trailing-slash bounces",
  loop: "Redirect loops",
};

// Display order matches how much a failure of that type hurts.
const TYPE_ORDER: ResourceType[] = [
  "anchor",
  "script",
  "stylesheet",
  "image",
  "css_url",
  "iframe",
  "media",
  "form_action",
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
  form_action: "form",
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
  redirects,
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

  const redirectRows = redirects
    ? [
        { label: "Permanent (301/308)", count: redirects.permanent },
        { label: "Temporary (302/303/307)", count: redirects.temporary },
        ...(Object.entries(redirects.flags ?? {}) as [RedirectFlag, number][])
          .filter(([, count]) => count > 0)
          .map(([flag, count]) => ({ label: FLAG_LABELS[flag] ?? flag, count })),
      ].filter((r) => r.count > 0)
    : [];

  if (!typeRows.length && !schemeRows.length && !hostRows.length && !redirectRows.length)
    return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="ds-container w-full mt-8 px-6 grid gap-4 md:grid-cols-3"
    >
      <Panel title="Link Types" rows={typeRows} mono />
      <Panel title="Top Hosts" rows={hostRows} mono />
      <Panel title="Link Schemes" rows={schemeRows} mono />
      {redirectRows.length > 0 && (
        <Panel
          title="Redirects"
          rows={redirectRows}
          footer={
            redirects && redirects.collapsible_rules > 0
              ? `${redirects.collapsible_rules} chain${
                  redirects.collapsible_rules === 1 ? "" : "s"
                } collapse to a single rule`
              : undefined
          }
        />
      )}
    </motion.div>
  );
}

function Panel({
  title,
  rows,
  mono,
  footer,
}: {
  title: string;
  rows: { label: string; count: number }[];
  mono?: boolean;
  footer?: string;
}) {
  if (!rows.length) return null;
  const max = Math.max(...rows.map((r) => r.count), 1);

  return (
    <section className="glass-card p-5">
      <h3
        className="text-[11px] uppercase tracking-widest mb-3"
        style={{ color: "var(--text-muted)" }}
      >
        {title}
      </h3>
      <ul className="space-y-2">
        {rows.map((row) => (
          <li key={row.label} className="text-xs">
            <div className="flex items-center justify-between gap-3">
              <span
                className={`truncate ${mono ? "font-mono" : ""}`}
                style={{ color: "var(--text-secondary)" }}
                title={row.label}
              >
                {row.label}
              </span>
              <span
                className="tabular-nums shrink-0"
                style={{ color: "var(--text-primary)" }}
              >
                {row.count}
              </span>
            </div>
            <div
              className="mt-1 h-1 rounded-full overflow-hidden"
              style={{ background: "rgba(28,28,46,0.04)" }}
            >
              <div
                className="h-full rounded-full"
                style={{
                  width: `${(row.count / max) * 100}%`,
                  background: "rgba(79,70,229,0.55)",
                }}
              />
            </div>
          </li>
        ))}
      </ul>
      {footer && (
        <p className="text-[11px] mt-3" style={{ color: "var(--text-muted)" }}>
          {footer}
        </p>
      )}
    </section>
  );
}
