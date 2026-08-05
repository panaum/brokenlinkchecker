import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  clientPathOf,
  deliveryPresence,
  presenceEnabled,
  presenceLineText,
  type PresenceDeliverable,
} from "./presence-shape.ts";

// ═══ PRESENCE — LinkSpy side ═════════════════════════════════════════════════
// Every state the delivery-presence line can be in, decided by pure functions.

function d(over: Partial<PresenceDeliverable> = {}): PresenceDeliverable {
  return {
    status: "IN_QA",
    tester_first_name: "Anaum",
    deep_link_path: "/dashboard/clients/c1/p1/pg1",
    ...over,
  };
}

// ── the flag ────────────────────────────────────────────────────────────────
test("PRESENCE flag: only the exact string '1' turns it on", () => {
  assert.equal(presenceEnabled({ PRESENCE: "1" }), true);
  assert.equal(presenceEnabled({ PRESENCE: "0" }), false);
  assert.equal(presenceEnabled({ PRESENCE: "true" }), false, "half-on is not a state");
  assert.equal(presenceEnabled({}), false);
});

test("flag off short-circuits the route before any upstream call", () => {
  const src = readFileSync("app/api/presence/delivery/route.ts", "utf8");
  const body = src.slice(src.indexOf("export async function GET"));
  const guard = body.indexOf("presenceEnabled(process.env)");
  const firstFetch = body.indexOf("fetch(");
  assert.ok(guard > -1 && guard < firstFetch,
    "the flag must be checked before the bridge is ever contacted");
  assert.match(body.slice(guard, guard + 200), /return NextResponse\.json\(\{ enabled: false \}\)/);
});

// ── quiet by design ─────────────────────────────────────────────────────────
test("nothing in QA yields a zero count, and the line is hidden", () => {
  const p = deliveryPresence([d({ status: "LIVE" }), d({ status: "IN_PROGRESS" })]);
  assert.equal(p.count, 0);
  assert.deepEqual(p.testers, []);
});

test("an empty or absent payload never throws", () => {
  for (const junk of [null, undefined, [], "nope" as unknown as PresenceDeliverable[]]) {
    assert.equal(deliveryPresence(junk).count, 0);
  }
});

// ── the line ────────────────────────────────────────────────────────────────
test("two deliverables in QA render with both testers", () => {
  const p = deliveryPresence([
    d({ tester_first_name: "Anaum" }),
    d({ tester_first_name: "Babar" }),
    d({ status: "LIVE", tester_first_name: "Malik" }),
  ]);
  assert.equal(p.count, 2);
  assert.deepEqual(p.testers, ["Anaum", "Babar"]);
  assert.equal(presenceLineText(p), "2 deliverables in QA · Anaum, Babar");
});

test("one deliverable is singular", () => {
  assert.equal(presenceLineText(deliveryPresence([d()])), "1 deliverable in QA · Anaum");
});

test("the same tester on two pages is named once", () => {
  const p = deliveryPresence([d({ tester_first_name: "Anaum" }), d({ tester_first_name: "Anaum" })]);
  assert.equal(p.count, 2);
  assert.deepEqual(p.testers, ["Anaum"]);
  assert.equal(presenceLineText(p), "2 deliverables in QA · Anaum");
});

test("tester order is stable, so a 60s poll never reshuffles the line", () => {
  const roster = [d({ tester_first_name: "Zara" }), d({ tester_first_name: "Anaum" })];
  assert.deepEqual(deliveryPresence(roster).testers, ["Zara", "Anaum"]);
  assert.deepEqual(deliveryPresence(roster).testers, ["Zara", "Anaum"]);
});

test("unassigned deliverables still count, with no names appended", () => {
  const p = deliveryPresence([d({ tester_first_name: null }), d({ tester_first_name: "  " })]);
  assert.equal(p.count, 2);
  assert.deepEqual(p.testers, []);
  assert.equal(presenceLineText(p), "2 deliverables in QA");
});

test("an older Dashboard that doesn't send the field yet degrades to counts only", () => {
  const p = deliveryPresence([{ status: "IN_QA", deep_link_path: "/dashboard/clients/c1/p1/pg1" }]);
  assert.equal(p.count, 1);
  assert.deepEqual(p.testers, []);
});

// ── handoff target ──────────────────────────────────────────────────────────
test("the client view is derived from a deliverable's deep link", () => {
  assert.equal(clientPathOf("/dashboard/clients/c1/p1/pg1"), "/dashboard/clients/c1");
  assert.equal(deliveryPresence([d()]).client_path, "/dashboard/clients/c1");
});

test("a malformed or absolute path is never turned into a handoff target", () => {
  for (const bad of [
    "https://evil.example/dashboard/clients/c1/p1/pg1",
    "/other/clients/c1",
    "/dashboard/clients/",
    "",
    null,
    undefined,
  ]) {
    assert.equal(clientPathOf(bad), null, `should refuse ${String(bad)}`);
  }
  assert.equal(deliveryPresence([d({ deep_link_path: "/nope" })]).client_path, null);
});

// ── the key, the flag and the signing all stay server-side ──────────────────
test("the component holds no secret, no flag and no bridge URL", () => {
  const src = readFileSync("components/DeliveryPresenceLine.tsx", "utf8");
  for (const forbidden of ["DASHBOARD_BRIDGE_KEY", "SPINE_SECRET", "process.env", "signHandoff"]) {
    assert.ok(!src.includes(forbidden), `${forbidden} must never reach the browser bundle`);
  }
  assert.match(src, /if \(!data \|\| !data\.enabled \|\| !data\.count\) return null;/,
    "no line, no wrapper, no reserved space when there is nothing to say");
  assert.ok(!src.includes("ds-skeleton"), "an awareness line must not flash a skeleton");
});

test("the route signs handoffs server-side and never writes", () => {
  const src = readFileSync("app/api/presence/delivery/route.ts", "utf8");
  assert.match(src, /handoffUrl\(/);
  assert.ok(!/\bPOST\b|\bPUT\b|\bDELETE\b|\bPATCH\b/.test(src), "read-only route: GET only");
});

// ── staleness over errors (constitution rule 6) ─────────────────────────────
test("the route is timeout-bounded, 60s cached, and downgrades to last-known-good", () => {
  const src = readFileSync("app/api/presence/delivery/route.ts", "utf8");
  assert.match(src, /CACHE_MS = 60 \* 1000/);
  assert.match(src, /AbortSignal\.timeout\(/, "a hung Dashboard must not hang the Overview");
  assert.match(src, /return NextResponse\.json\(hit \? shape\(hit, true\) : QUIET\)/,
    "unreachable serves cache marked stale, or says nothing — never an error");
});

// ── the existing Delivery panel is untouched in both flag states ────────────
test("presence does not reach into /api/delivery or DeliveryPanel", () => {
  // Code only — these files explain themselves in prose that names the very
  // things the code must not touch.
  const code = (p: string) =>
    readFileSync(p, "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

  const route = code("app/api/presence/delivery/route.ts");
  assert.ok(!route.includes("/api/delivery"),
    "presence calls the Dashboard producer directly — it has its own 60s window");
  assert.match(route, /registry-bridge\/delivery/, "same producer, separate consumer");

  const panel = code("components/DeliveryPanel.tsx");
  assert.ok(!/presence/i.test(panel),
    "DeliveryPanel must be byte-identical to before this feature");
});
