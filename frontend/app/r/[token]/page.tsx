import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { SharedReport } from "@/types";
import PublicReport from "@/components/PublicReport";

export const dynamic = "force-dynamic";

const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

async function fetchReport(token: string): Promise<SharedReport | null> {
  try {
    const res = await fetch(`${backend()}/api/r/${token}`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as SharedReport;
  } catch {
    return null;
  }
}

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ token: string }>;
}): Promise<Metadata> {
  const { token } = await params;
  const report = await fetchReport(token);
  if (!report) return { title: "Report not found — LinkSpy" };
  const domain = domainOf(report.url);
  return {
    title: `${domain} — Link health ${report.health_score}/100 | LinkSpy`,
    description: `LinkSpy scanned ${domain}: ${report.broken_count} broken, ${report.dead_cta_count} dead CTAs across ${report.total_links} links.`,
  };
}

export default async function SharedReportPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  const report = await fetchReport(token);
  if (!report) notFound();
  return <PublicReport report={report} />;
}
