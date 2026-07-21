"use client";

import { useState, useRef, useEffect } from "react";
import { Search, X, ChevronDown } from "lucide-react";
import { DiffFilter, FilterType, LinkResult, ScanDiff, SortOption } from "@/types";

interface FilterBarProps {
  results: LinkResult[];
  filter: FilterType;
  onFilterChange: (f: FilterType) => void;
  sortOption: SortOption;
  onSortChange: (s: SortOption) => void;
  search: string;
  onSearchChange: (s: string) => void;
  zoneFilter: string;
  onZoneFilterChange: (z: string) => void;
  filteredCount: number;
  /** Baseline diff. Without a baseline there is nothing to filter by. */
  diff?: ScanDiff | null;
  diffFilter?: DiffFilter;
  onDiffFilterChange?: (d: DiffFilter) => void;
}

const DIFF_ITEMS: { label: string; value: DiffFilter; color: string; bg: string }[] = [
  { label: "All", value: "all", color: "#1c1c2e", bg: "rgba(28,28,46,0.04)" },
  { label: "New", value: "new", color: "#e05c5c", bg: "rgba(224,92,92,0.12)" },
  { label: "Recurring", value: "recurring", color: "#f5a623", bg: "rgba(245,166,35,0.12)" },
  { label: "Fixed", value: "fixed", color: "#4caf7d", bg: "rgba(76,175,125,0.12)" },
];

function diffCount(results: LinkResult[], diff: ScanDiff, value: DiffFilter): number {
  if (value === "all") return results.length;
  // Fixed findings are gone from the page, so they never appear in `results`.
  if (value === "fixed") return diff.fixed;
  return results.filter((r) => r.diff_status === value).length;
}

const ZONES = [
  "All zones",
  "Navigation",
  "Header",
  "CTA",
  "Body text",
  "Footer",
  "Other",
  "Dead CTA",
];

const SORT_OPTIONS: { label: string; value: SortOption }[] = [
  { label: "Status", value: "status" },
  { label: "Zone", value: "zone" },
  { label: "Response Time", value: "response_ms" },
];

function countByLabel(results: LinkResult[], label: string): number {
  if (label === "all") return results.length;
  if (label === "blocked")
    return results.filter(
      (r) => r.label === "blocked" || r.label === "forbidden"
    ).length;
  return results.filter((r) => r.label === label).length;
}

interface StatusFilterItem {
  label: string;
  value: FilterType;
  color: string;
  bg: string;
}

const STATUS_ITEMS: StatusFilterItem[] = [
  { label: "All", value: "all", color: "#1c1c2e", bg: "rgba(28,28,46,0.04)" },
  { label: "Working", value: "ok", color: "#4caf7d", bg: "rgba(76,175,125,0.12)" },
  { label: "Broken", value: "broken", color: "#e05c5c", bg: "rgba(224,92,92,0.12)" },
  { label: "Dead Button", value: "dead_cta", color: "#f5a623", bg: "rgba(245,166,35,0.12)" },
  { label: "Redirected", value: "redirect", color: "#f5a623", bg: "rgba(245,166,35,0.12)" },
  { label: "Can't Verify", value: "blocked", color: "#4f46e5", bg: "rgba(79,70,229,0.12)" },
  { label: "Not Responding", value: "timeout", color: "#7a7a8c", bg: "rgba(122,122,140,0.12)" },
  { label: "Conn. Failed", value: "error", color: "#e05c5c", bg: "rgba(224,92,92,0.12)" },
];

export default function FilterBar({
  results,
  filter,
  onFilterChange,
  sortOption,
  onSortChange,
  search,
  onSearchChange,
  zoneFilter,
  onZoneFilterChange,
  filteredCount,
  diff,
  diffFilter = "all",
  onDiffFilterChange,
}: FilterBarProps) {
  const [zoneOpen, setZoneOpen] = useState(false);
  const [sortOpen, setSortOpen] = useState(false);
  const zoneRef = useRef<HTMLDivElement>(null);
  const sortRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (zoneRef.current && !zoneRef.current.contains(e.target as Node)) setZoneOpen(false);
      if (sortRef.current && !sortRef.current.contains(e.target as Node)) setSortOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const showDiffFilter = diff?.has_baseline === true && !!onDiffFilterChange;

  return (
    <div className="w-full max-w-5xl mx-auto mt-6 px-4">
      <div className="flex flex-col gap-4">
        {/* Diff filter — only meaningful once a baseline exists */}
        {showDiffFilter && (
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="text-[11px] uppercase tracking-widest mr-1"
              style={{ color: "var(--text-muted)" }}
            >
              Since last scan
            </span>
            {DIFF_ITEMS.map((item) => {
              const count = diffCount(results, diff!, item.value);
              const isActive = diffFilter === item.value;
              if (item.value !== "all" && count === 0) return null;
              return (
                <button
                  key={item.value}
                  onClick={() => onDiffFilterChange!(item.value)}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-xl transition-all cursor-pointer"
                  style={{
                    background: isActive
                      ? "var(--signal)"
                      : item.bg,
                    border: isActive
                      ? "1px solid rgba(79,70,229,0.6)"
                      : `1px solid ${item.color}22`,
                    fontFamily: "var(--font-poppins), Poppins, sans-serif",
                    fontWeight: isActive ? 600 : 400,
                    fontSize: "12px",
                    color: isActive ? "#fff" : item.color,
                  }}
                >
                  {item.label}
                  <span
                    className="rounded-full px-1.5 py-0.5 text-[11px] tabular-nums"
                    style={{
                      background: isActive
                        ? "rgba(255,255,255,0.2)"
                        : "rgba(28,28,46,0.06)",
                    }}
                  >
                    {count}
                  </span>
                </button>
              );
            })}
          </div>
        )}

        {/* Status filter cards */}
        <div className="flex flex-wrap gap-2">
          {STATUS_ITEMS.map((item) => {
            const count = countByLabel(results, item.value);
            const isActive = filter === item.value;
            if (item.value !== "all" && count === 0) return null;
            return (
              <button
                key={item.value}
                onClick={() => onFilterChange(item.value)}
                className="flex items-center gap-2 px-3 py-2 rounded-xl transition-all cursor-pointer"
                style={{
                  background: isActive
                    ? "var(--signal)"
                    : item.bg,
                  border: isActive
                    ? "1px solid rgba(79,70,229,0.6)"
                    : `1px solid ${item.color}22`,
                  boxShadow: isActive
                    ? "0 0 12px rgba(79,70,229,0.3)"
                    : "none",
                  fontFamily: "var(--font-poppins), Poppins, sans-serif",
                  fontWeight: isActive ? 600 : 400,
                  fontSize: "13px",
                  color: isActive ? "#fff" : item.color,
                }}
              >
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{ background: isActive ? "#fff" : item.color }}
                />
                {item.label}
                <span
                  className="rounded-full px-1.5 py-0.5 text-xs tabular-nums"
                  style={{
                    background: isActive
                      ? "rgba(255,255,255,0.2)"
                      : "rgba(28,28,46,0.06)",
                    color: isActive ? "#fff" : "var(--text-secondary)",
                    fontWeight: 600,
                  }}
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Second row: Zone dropdown, Search, Sort */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Zone dropdown */}
          <div ref={zoneRef} className="relative">
            <button
              onClick={() => { setZoneOpen((p) => !p); setSortOpen(false); }}
              className="flex items-center gap-2 px-3 py-2 rounded-xl transition-all cursor-pointer"
              style={{
                background: "rgba(28,28,46,0.04)",
                border: "1px solid var(--border-subtle)",
                fontFamily: "var(--font-poppins), Poppins, sans-serif",
                fontSize: "13px",
                fontWeight: 500,
                color: zoneFilter !== "All zones" ? "var(--signal)" : "var(--text-secondary)",
              }}
            >
              {zoneFilter}
              <ChevronDown size={14} style={{ transform: zoneOpen ? "rotate(180deg)" : "none", transition: "transform 0.2s" }} />
            </button>
            {zoneOpen && (
              <div
                className="absolute top-full mt-2 left-0 z-50 rounded-xl overflow-hidden"
                style={{
                  background: "var(--surface-card)",
                  border: "1px solid var(--border-subtle)",
                  minWidth: "160px",
                  boxShadow: "var(--elev-3)",
                }}
              >
                {ZONES.map((zone) => (
                  <button
                    key={zone}
                    onClick={() => { onZoneFilterChange(zone); setZoneOpen(false); }}
                    className="w-full text-left px-4 py-2.5 transition-colors cursor-pointer"
                    style={{
                      fontFamily: "var(--font-poppins), Poppins, sans-serif",
                      fontSize: "13px",
                      fontWeight: zoneFilter === zone ? 600 : 400,
                      color: zoneFilter === zone ? "var(--signal)" : "var(--text-secondary)",
                      background: zoneFilter === zone ? "rgba(79,70,229,0.08)" : "transparent",
                    }}
                    onMouseEnter={(e) => {
                      if (zoneFilter !== zone) (e.currentTarget as HTMLButtonElement).style.background = "rgba(28,28,46,0.06)";
                    }}
                    onMouseLeave={(e) => {
                      if (zoneFilter !== zone) (e.currentTarget as HTMLButtonElement).style.background = "transparent";
                    }}
                  >
                    {zone}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Search */}
          <div
            className="flex items-center gap-2 flex-1 px-3 py-2 rounded-xl"
            style={{
              background: "rgba(28,28,46,0.04)",
              border: "1px solid var(--border-subtle)",
              minWidth: "180px",
            }}
          >
            <Search size={14} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
            <input
              type="text"
              value={search}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Search URLs or link text…"
              className="flex-1 bg-transparent outline-none"
              style={{
                fontFamily: "var(--font-poppins), Poppins, sans-serif",
                fontSize: "13px",
                color: "var(--text-primary)",
                caretColor: "var(--signal)",
              }}
            />
            {search && (
              <button onClick={() => onSearchChange("")} className="cursor-pointer">
                <X size={13} style={{ color: "var(--text-muted)" }} />
              </button>
            )}
          </div>

          {/* Sort dropdown */}
          <div ref={sortRef} className="relative">
            <button
              onClick={() => { setSortOpen((p) => !p); setZoneOpen(false); }}
              className="flex items-center gap-2 px-3 py-2 rounded-xl transition-all cursor-pointer"
              style={{
                background: "rgba(28,28,46,0.04)",
                border: "1px solid var(--border-subtle)",
                fontFamily: "var(--font-poppins), Poppins, sans-serif",
                fontSize: "13px",
                fontWeight: 500,
                color: "var(--text-secondary)",
                whiteSpace: "nowrap",
              }}
            >
              Sort: {SORT_OPTIONS.find((o) => o.value === sortOption)?.label}
              <ChevronDown size={14} style={{ transform: sortOpen ? "rotate(180deg)" : "none", transition: "transform 0.2s" }} />
            </button>
            {sortOpen && (
              <div
                className="absolute top-full mt-2 right-0 z-50 rounded-xl overflow-hidden"
                style={{
                  background: "var(--surface-card)",
                  border: "1px solid var(--border-subtle)",
                  minWidth: "160px",
                  boxShadow: "var(--elev-3)",
                }}
              >
                {SORT_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => { onSortChange(opt.value); setSortOpen(false); }}
                    className="w-full text-left px-4 py-2.5 transition-colors cursor-pointer"
                    style={{
                      fontFamily: "var(--font-poppins), Poppins, sans-serif",
                      fontSize: "13px",
                      fontWeight: sortOption === opt.value ? 600 : 400,
                      color:
                        sortOption === opt.value
                          ? "var(--signal)"
                          : "var(--text-secondary)",
                      background:
                        sortOption === opt.value
                          ? "rgba(79,70,229,0.08)"
                          : "transparent",
                    }}
                    onMouseEnter={(e) => {
                      if (sortOption !== opt.value)
                        (e.currentTarget as HTMLButtonElement).style.background =
                          "rgba(28,28,46,0.06)";
                    }}
                    onMouseLeave={(e) => {
                      if (sortOption !== opt.value)
                        (e.currentTarget as HTMLButtonElement).style.background =
                          "transparent";
                    }}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Result count */}
          <span
            style={{
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              fontSize: "12px",
              fontWeight: 400,
              color: "var(--text-muted)",
              whiteSpace: "nowrap",
            }}
          >
            {filteredCount} link{filteredCount !== 1 ? "s" : ""}
          </span>
        </div>
      </div>
    </div>
  );
}
