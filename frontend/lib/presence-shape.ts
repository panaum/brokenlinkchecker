// PRESENCE (Seam 3) — pure shaping for the delivery-presence line on Site
// Detail. No I/O, no secrets, no React, so every state is unit-testable.
//
// The line's contract: it is QUIET BY DEFAULT. Nothing in QA means no line at
// all — the Overview stays exactly as it is today.

export type PresenceDeliverable = {
  status: string;
  tester_first_name?: string | null;
  deep_link_path?: string | null;
};

export type DeliveryPresence = {
  // Rendered only when count > 0.
  count: number;
  testers: string[];
  // App-relative path on the Dashboard, signed into a handoff before it ships.
  client_path: string | null;
};

// LinkSpy and the Dashboard share one status vocabulary (constitution rule 8).
const IN_QA = "IN_QA";

/**
 * The Dashboard client view that owns these deliverables, derived from a
 * deliverable's deep link (/dashboard/clients/{client}/{project}/{page}).
 * Returns null for anything that isn't that exact shape — a malformed path is
 * never signed into a handoff token.
 */
export function clientPathOf(deepLinkPath: string | null | undefined): string | null {
  if (typeof deepLinkPath !== "string" || !deepLinkPath.startsWith("/dashboard/clients/")) return null;
  const parts = deepLinkPath.split("/").filter(Boolean); // dashboard, clients, {c}, …
  const clientId = parts[2];
  return clientId ? `/dashboard/clients/${clientId}` : null;
}

/**
 * Fold a delivery-bridge payload into the one line's worth of facts.
 *
 * Testers are de-duplicated (two pages, one tester reads as one name) and kept
 * in bridge order, which is deliverable creation order — stable across polls,
 * so the line doesn't reshuffle itself every 60 seconds.
 */
export function deliveryPresence(deliverables: PresenceDeliverable[] | null | undefined): DeliveryPresence {
  const inQa = (Array.isArray(deliverables) ? deliverables : []).filter(
    (d) => d && d.status === IN_QA,
  );

  const testers: string[] = [];
  for (const d of inQa) {
    const name = typeof d.tester_first_name === "string" ? d.tester_first_name.trim() : "";
    if (name && !testers.includes(name)) testers.push(name);
  }

  const withLink = inQa.find((d) => clientPathOf(d.deep_link_path));
  return {
    count: inQa.length,
    testers,
    client_path: withLink ? clientPathOf(withLink.deep_link_path) : null,
  };
}

/** "2 deliverables in QA · Anaum, Babar" — or "…in QA" when nobody is assigned. */
export function presenceLineText(p: DeliveryPresence): string {
  const head = `${p.count} deliverable${p.count === 1 ? "" : "s"} in QA`;
  return p.testers.length ? `${head} · ${p.testers.join(", ")}` : head;
}

/** The flag. Only the exact string "1" counts — half-on is not a state. */
export function presenceEnabled(env: Record<string, string | undefined>): boolean {
  return env.PRESENCE === "1";
}
