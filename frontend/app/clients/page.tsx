"use client";

import React, { useEffect, useState, useCallback, useMemo } from "react";
import NavBar from "@/components/NavBar";
import { DashboardSite } from "@/types";
import { Avatar } from "@/components/Avatar";
import { Plus, Users, Link2, Copy, Check, X, Loader2, Mail } from "lucide-react";

interface Client { id: string; name: string; created_at?: string }
interface Resource { id: string; title: string; url: string; visible: boolean }
interface Invite {
  token: string; email: string; client_id: string | null; role: string;
  created_at?: string; expires_at?: string; accepted_at?: string | null; revoked?: boolean;
}

function domainOf(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
}
function inviteStatus(i: Invite): { word: string; cls: string } {
  if (i.revoked) return { word: "Revoked", cls: "ds-status-neutral" };
  if (i.accepted_at) return { word: "Active", cls: "ds-status-healthy" };
  if (i.expires_at && new Date(i.expires_at) < new Date()) return { word: "Expired", cls: "ds-status-broken" };
  return { word: "Invited", cls: "ds-status-attention" };
}

export default function ClientsPage() {
  const [clients, setClients] = useState<Client[]>([]);
  const [sites, setSites] = useState<DashboardSite[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [c, d, i] = await Promise.all([
        fetch("/api/clients").then((r) => r.json()).catch(() => ({ clients: [] })),
        fetch("/api/dashboard").then((r) => r.json()).catch(() => ({ sites: [] })),
        fetch("/api/invites").then((r) => r.json()).catch(() => ({ invites: [] })),
      ]);
      setClients(c.clients ?? []);
      setSites(d.sites ?? []);
      setInvites(i.invites ?? []);
      if (c.setup_required || (c.error && !c.clients)) {
        setNotice("Client management needs the multi-tenancy migration + backfill applied first.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { document.title = "Clients | LinkSpy"; load(); }, [load]);

  const createClient = async () => {
    const name = newName.trim();
    if (!name) { setNotice("Type a client name."); return; }
    setNotice(null);
    try {
      const res = await fetch(`/api/clients?name=${encodeURIComponent(name)}`, { method: "POST" });
      let body: { error?: string } = {};
      try { body = await res.json(); } catch { /* non-JSON */ }
      if (!res.ok) {
        setNotice(`Couldn't create client — HTTP ${res.status}${body.error ? `: ${body.error}` : ""}.`);
        return;
      }
      setNewName("");
      setShowModal(false);
      load();
    } catch {
      setNotice("Couldn't reach the server to create the client.");
    }
  };

  return (
    <div className="min-h-screen" style={{ background: "var(--surface-page)", paddingTop: 56 }}>
      <NavBar />
      <div className="ds-container" style={{ maxWidth: "var(--content-max)", padding: "40px 24px 64px", display: "flex", flexDirection: "column", gap: "var(--space-6)" }}>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
          <div>
            <h1 className="ds-text-primary font-display" style={{ fontSize: "var(--text-display)", fontWeight: 700, letterSpacing: "-0.5px" }}>Clients</h1>
            <p className="ds-text-secondary" style={{ fontSize: "var(--text-body)", marginTop: 2 }}>
              {clients.length} {clients.length === 1 ? "client" : "clients"} · portal access &amp; site assignments
            </p>
          </div>
          <button className="ds-btn-primary" onClick={() => { setNewName(""); setNotice(null); setShowModal(true); }} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
            <Plus size={16} /> Add client
          </button>
        </div>

        {notice && (
          <div className="ds-card ds-card-pad ds-text-secondary" style={{ fontSize: "var(--text-body)", borderColor: "var(--status-attention)" }}>
            {notice}
          </div>
        )}

        {loading ? (
          <div className="ds-card ds-card-pad"><div className="ds-skeleton" style={{ height: 80 }} /></div>
        ) : clients.length === 0 ? (
          <div className="ds-card ds-card-pad ds-text-secondary" style={{ textAlign: "center", padding: 48, fontSize: "var(--text-body)" }}>
            No clients yet. Add one, then assign its sites and invite a viewer.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
            {clients.map((c) => (
              <ClientCard
                key={c.id}
                client={c}
                sites={sites}
                invites={invites.filter((i) => i.client_id === c.id)}
                expanded={expanded === c.id}
                onToggle={() => setExpanded((e) => (e === c.id ? null : c.id))}
                onChanged={load}
              />
            ))}
          </div>
        )}
      </div>

      {/* Add-client modal — same proven pattern as the dashboard's Add-site. */}
      {showModal && (
        <div
          onMouseDown={(e) => { if (e.target === e.currentTarget) setShowModal(false); }}
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16, zIndex: 200 }}
        >
          <div className="ds-card ds-card-pad" style={{ width: "100%", maxWidth: 420 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
              <h3 className="ds-text-primary font-display" style={{ fontSize: "var(--text-heading)", fontWeight: 700 }}>Add client</h3>
              <button onClick={() => setShowModal(false)} className="ds-text-muted" style={{ background: "none", border: "none", cursor: "pointer" }}><X size={18} /></button>
            </div>
            <form onSubmit={(e) => { e.preventDefault(); createClient(); }}>
              <input
                autoFocus
                id="new-client-name"
                name="new-client-name"
                autoComplete="off"
                data-gramm="false"
                data-enable-grammarly="false"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Client name, e.g. Thermalboard"
                style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)", borderRadius: "var(--radius-md)", padding: "10px 12px", fontSize: "var(--text-body)", outline: "none" }}
              />
              {notice && <div className="ds-status ds-status-broken" style={{ fontSize: "var(--text-caption)", marginTop: 10 }}><span className="ds-status-dot" />{notice}</div>}
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
                <button type="button" className="ds-btn-ghost" onClick={() => setShowModal(false)}>Cancel</button>
                <button type="submit" className="ds-btn-primary">Create client</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function ClientCard({ client, sites, invites, expanded, onToggle, onChanged }: {
  client: Client; sites: DashboardSite[]; invites: Invite[];
  expanded: boolean; onToggle: () => void; onChanged: () => void;
}) {
  const assigned = useMemo(() => sites.filter((s) => (s as unknown as { client_id?: string }).client_id === client.id), [sites, client.id]);
  const unassigned = useMemo(() => sites.filter((s) => !(s as unknown as { client_id?: string }).client_id), [sites]);
  const active = invites.filter((i) => i.accepted_at && !i.revoked).length;
  const pending = invites.filter((i) => !i.accepted_at && !i.revoked).length;

  // Aggregate health across the client's sites (worst-site drives the color).
  const health = useMemo(() => {
    let openIssues = 0, worst: number | null = null, scanned = 0, anyBroken = false, anyAttn = false;
    for (const s of assigned) {
      const scans = [...(s.scans ?? [])].sort((a, b) => new Date(a.scanned_at).getTime() - new Date(b.scanned_at).getTime());
      const latest = scans[scans.length - 1];
      if (!latest) continue;
      scanned++;
      openIssues += (latest.broken_count ?? 0) + (latest.dead_cta_count ?? 0);
      if ((latest.broken_count ?? 0) > 0) anyBroken = true;
      else if ((latest.dead_cta_count ?? 0) > 0) anyAttn = true;
      if (worst === null || latest.health_score < worst) worst = latest.health_score;
    }
    const cls = scanned === 0 ? "ds-status-neutral" : anyBroken ? "ds-status-broken" : anyAttn ? "ds-status-attention" : "ds-status-healthy";
    const word = scanned === 0 ? "Not scanned" : anyBroken ? "Needs attention" : anyAttn ? "Minor issues" : "All healthy";
    return { openIssues, worst, cls, word, scanned };
  }, [assigned]);

  return (
    <div className={`ds-card ds-card-pad ${expanded ? "" : "ds-card-hover"}`}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, cursor: "pointer" }} onClick={onToggle}>
        <Avatar name={client.name} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="ds-text-primary" style={{ fontSize: "var(--text-body)", fontWeight: 600 }}>{client.name}</div>
          <div className="ds-text-muted" style={{ fontSize: "var(--text-caption)" }}>
            {assigned.length} {assigned.length === 1 ? "site" : "sites"}
            {active > 0 && <> · <span style={{ color: "var(--status-healthy)" }}>{active} active</span></>}
            {pending > 0 && <> · <span style={{ color: "var(--status-attention)" }}>{pending} invited</span></>}
          </div>
        </div>
        {/* Aggregate health at a glance */}
        <div style={{ display: "flex", alignItems: "center", gap: 16, flexShrink: 0 }}>
          {health.worst !== null && (
            <span className="font-mono" style={{ fontSize: 20, fontWeight: 700, color: "var(--signal)" }}>{health.worst}</span>
          )}
          <div style={{ textAlign: "right" }}>
            <span className={`ds-status ${health.cls}`}><span className="ds-status-dot" />{health.word}</span>
            {health.openIssues > 0 && (
              <div className="ds-text-muted" style={{ fontSize: 11, marginTop: 2 }}>{health.openIssues} open {health.openIssues === 1 ? "issue" : "issues"}</div>
            )}
          </div>
          <span className="ds-text-muted" style={{ fontSize: "var(--text-caption)", width: 44, textAlign: "right" }}>{expanded ? "Hide" : "Manage"}</span>
        </div>
      </div>

      {expanded && (
        <div style={{ marginTop: "var(--space-5)", display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-5)" }}>
            <SitesPanel clientId={client.id} assigned={assigned} unassigned={unassigned} onChanged={onChanged} />
            <InvitesPanel clientId={client.id} invites={invites} onChanged={onChanged} />
          </div>
          <ResourcesPanel clientId={client.id} />
        </div>
      )}
    </div>
  );
}

function SitesPanel({ clientId, assigned, unassigned, onChanged }: {
  clientId: string; assigned: DashboardSite[]; unassigned: DashboardSite[]; onChanged: () => void;
}) {
  const assign = async (siteId: string, cid: string) => {
    await fetch(`/api/sites/${siteId}/assign-client?client_id=${encodeURIComponent(cid)}`, { method: "POST" }).catch(() => {});
    onChanged();
  };
  return (
    <div>
      <div className="font-mono ds-text-muted" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 10 }}>
        <Link2 size={12} style={{ display: "inline", verticalAlign: "middle", marginRight: 6 }} />Sites
      </div>
      {assigned.length === 0 ? (
        <p className="ds-text-muted" style={{ fontSize: "var(--text-caption)", marginBottom: 10 }}>No sites assigned yet.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 10 }}>
          {assigned.map((s) => (
            <div key={s.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, fontSize: "var(--text-caption)" }}>
              <span className="font-mono ds-text-secondary" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{domainOf(s.url)}</span>
              <button onClick={() => assign(s.id, "")} className="ds-text-muted" style={{ background: "none", border: "none", cursor: "pointer", flexShrink: 0 }} title="Unassign"><X size={13} /></button>
            </div>
          ))}
        </div>
      )}
      {unassigned.length > 0 && (
        <select
          defaultValue=""
          onChange={(e) => { if (e.target.value) assign(e.target.value, clientId); e.target.value = ""; }}
          style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border-subtle)", color: "var(--text-secondary)", borderRadius: "var(--radius-sm)", padding: "8px 10px", fontSize: "var(--text-caption)" }}
        >
          <option value="">+ assign a site…</option>
          {unassigned.map((s) => <option key={s.id} value={s.id}>{domainOf(s.url)}</option>)}
        </select>
      )}
    </div>
  );
}

function InvitesPanel({ clientId, invites, onChanged }: {
  clientId: string; invites: Invite[]; onChanged: () => void;
}) {
  const [email, setEmail] = useState("");
  const [creating, setCreating] = useState(false);
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const invite = async () => {
    if (!email.trim()) return;
    setCreating(true); setError(null); setLink(null);
    try {
      const res = await fetch(`/api/invites?email=${encodeURIComponent(email.trim())}&client_id=${encodeURIComponent(clientId)}`, { method: "POST" });
      const body = await res.json();
      if (!res.ok) { setError(body.error || "Could not create invite."); return; }
      setLink(body.accept_url);
      setEmail("");
      onChanged();
    } finally { setCreating(false); }
  };

  const revoke = async (token: string) => {
    await fetch(`/api/invites/${token}`, { method: "DELETE" }).catch(() => {});
    onChanged();
  };

  const copy = async () => {
    if (!link) return;
    try { await navigator.clipboard.writeText(link); setCopied(true); setTimeout(() => setCopied(false), 800); } catch { /* ignore */ }
  };

  return (
    <div>
      <div className="font-mono ds-text-muted" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 10 }}>
        <Users size={12} style={{ display: "inline", verticalAlign: "middle", marginRight: 6 }} />Portal viewers
      </div>
      {invites.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 10 }}>
          {invites.map((i) => {
            const st = inviteStatus(i);
            return (
              <div key={i.token} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, fontSize: "var(--text-caption)" }}>
                <span className="ds-text-secondary" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{i.email}</span>
                <span style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                  <span className={`ds-status ${st.cls}`}><span className="ds-status-dot" />{st.word}</span>
                  {!i.revoked && !i.accepted_at && (
                    <button onClick={() => revoke(i.token)} className="ds-text-muted" style={{ background: "none", border: "none", cursor: "pointer" }} title="Revoke"><X size={13} /></button>
                  )}
                </span>
              </div>
            );
          })}
        </div>
      )}
      <div style={{ display: "flex", gap: 6 }}>
        <input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") invite(); }}
          placeholder="client@company.com"
          style={{ flex: 1, minWidth: 0, background: "var(--surface-raised)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)", borderRadius: "var(--radius-sm)", padding: "8px 10px", fontSize: "var(--text-caption)", outline: "none" }}
        />
        <button className="ds-btn-ghost" onClick={invite} disabled={creating} style={{ padding: "0 12px" }}>
          {creating ? <Loader2 size={14} className="animate-spin" /> : <Mail size={14} />}
        </button>
      </div>
      {error && <div className="ds-status ds-status-broken" style={{ fontSize: "var(--text-caption)", marginTop: 8 }}><span className="ds-status-dot" />{error}</div>}
      {link && (
        <div style={{ marginTop: 8, display: "flex", gap: 6, alignItems: "center" }}>
          <input readOnly value={link} onFocus={(e) => e.currentTarget.select()} className="font-mono" style={{ flex: 1, minWidth: 0, background: "rgba(28,28,46,0.04)", border: "1px solid var(--border-subtle)", color: "var(--text-secondary)", borderRadius: "var(--radius-sm)", padding: "7px 9px", fontSize: 11 }} />
          <button className="ds-btn-primary" onClick={copy} style={{ padding: "0 10px" }}>{copied ? <Check size={14} /> : <Copy size={14} />}</button>
        </div>
      )}
      {link && <div className="ds-text-muted" style={{ fontSize: 11, marginTop: 6 }}>Share this link with the client — it&apos;s their login.</div>}
    </div>
  );
}

function ResourcesPanel({ clientId }: { clientId: string }) {
  const [resources, setResources] = useState<Resource[]>([]);
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const r = await fetch(`/api/clients/${clientId}/resources`).then((x) => x.json()).catch(() => ({ resources: [] }));
    setResources(r.resources ?? []);
  }, [clientId]);
  useEffect(() => { load(); }, [load]);

  const add = async () => {
    if (!title.trim() || !url.trim()) return;
    setBusy(true);
    try {
      const u = /^https?:\/\//.test(url.trim()) ? url.trim() : `https://${url.trim()}`;
      await fetch(`/api/clients/${clientId}/resources?title=${encodeURIComponent(title.trim())}&url=${encodeURIComponent(u)}&visible=true`, { method: "POST" });
      setTitle(""); setUrl(""); load();
    } finally { setBusy(false); }
  };
  const toggle = async (id: string, visible: boolean) => { await fetch(`/api/resources/${id}?visible=${!visible}`, { method: "PATCH" }); load(); };
  const remove = async (id: string) => { await fetch(`/api/resources/${id}`, { method: "DELETE" }); load(); };

  const field = { background: "var(--surface-raised)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)", borderRadius: "var(--radius-sm)", padding: "8px 10px", fontSize: "var(--text-caption)", outline: "none" } as const;

  return (
    <div>
      <div className="font-mono ds-text-muted" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 10 }}>
        <Link2 size={12} style={{ display: "inline", verticalAlign: "middle", marginRight: 6 }} />Resources <span style={{ textTransform: "none", letterSpacing: 0 }}>(QA certificate, staging, Figma…)</span>
      </div>
      {resources.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 10 }}>
          {resources.map((r) => (
            <div key={r.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, fontSize: "var(--text-caption)" }}>
              <a href={r.url} target="_blank" rel="noreferrer" className="ds-text-primary" style={{ textDecoration: "none", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 }}>{r.title}</a>
              <span style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
                <button onClick={() => toggle(r.id, r.visible)} title="Toggle client visibility" style={{ background: "none", border: "none", cursor: "pointer", fontSize: 11, color: r.visible ? "var(--status-healthy)" : "var(--text-muted)" }}>
                  {r.visible ? "Client-visible" : "Hidden"}
                </button>
                <button onClick={() => remove(r.id)} className="ds-text-muted" style={{ background: "none", border: "none", cursor: "pointer" }} title="Remove"><X size={13} /></button>
              </span>
            </div>
          ))}
        </div>
      )}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Label, e.g. QA certificate" data-gramm="false" style={{ ...field, flex: "1 1 140px", minWidth: 0 }} />
        <input value={url} onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") add(); }} placeholder="https://…" data-gramm="false" style={{ ...field, flex: "2 1 200px", minWidth: 0 }} />
        <button className="ds-btn-ghost" onClick={add} disabled={busy} style={{ padding: "0 12px" }}>
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
        </button>
      </div>
    </div>
  );
}
