"use client";

import { useState, useRef, useEffect } from "react";
import { Search, X, ChevronDown } from "lucide-react";
import { FilterType, LinkResult, SortOption } from "@/types";

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
  { label: "All", value: "all", color: "#fff", bg: "rgba(255,255,255,0.08)" },
  { label: "Working", value: "ok", color: "#4ade80", bg: "rgba(74,222,128,0.12)" },
  { label: "Broken", value: "broken", color: "#f87171", bg: "rgba(248,113,113,0.12)" },
  { label: "Dead Button", value: "dead_cta", color: "#fbbf24", bg: "rgba(251,191,36,0.12)" },
  { label: "Redirected", value: "redirect", color: "#fb923c", bg: "rgba(251,146,60,0.12)" },
  { label: "Can't Verify", value: "blocked", color: "#e879f9", bg: "rgba(232,121,249,0.12)" },
  { label: "Not Responding", value: "timeout", color: "#94a3b8", bg: "rgba(148,163,184,0.12)" },
  { label: "Conn. Failed", value: "error", color: "#f87171", bg: "rgba(248,113,113,0.12)" },
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

  return (
    <div className="w-full max-w-5xl mx-auto mt-6 px-4">
      <div className="flex flex-col gap-4">
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
                    ? "linear-gradient(132deg,rgb(65,0,153),rgb(138,26,155))"
                    : item.bg,
                  border: isActive
                    ? "1px solid rgba(138,26,155,0.6)"
                    : `1px solid ${item.color}22`,
                  boxShadow: isActive
                    ? "0 0 12px rgba(138,26,155,0.3)"
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
                      : "rgba(255,255,255,0.08)",
                    color: isActive ? "#fff" : "rgba(255,255,255,0.6)",
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
                background: "rgba(255,255,255,0.05)",
                border: "1px solid rgba(255,255,255,0.1)",
                fontFamily: "var(--font-poppins), Poppins, sans-serif",
                fontSize: "13px",
                fontWeight: 500,
                color: zoneFilter !== "All zones" ? "#e879f9" : "rgba(255,255,255,0.6)",
              }}
            >
              {zoneFilter}
              <ChevronDown size={14} style={{ transform: zoneOpen ? "rotate(180deg)" : "none", transition: "transform 0.2s" }} />
            </button>
            {zoneOpen && (
              <div
                className="absolute top-full mt-2 left-0 z-50 rounded-xl overflow-hidden"
                style={{
                  background: "rgba(15,8,30,0.97)",
                  backdropFilter: "blur(16px)",
                  border: "1px solid rgba(255,255,255,0.12)",
                  minWidth: "160px",
                  boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
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
                      color: zoneFilter === zone ? "#e879f9" : "rgba(255,255,255,0.65)",
                      background: zoneFilter === zone ? "rgba(232,121,249,0.08)" : "transparent",
                    }}
                    onMouseEnter={(e) => {
                      if (zoneFilter !== zone) (e.currentTarget as HTMLButtonElement).style.background = "rgba(255,255,255,0.04)";
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
              background: "rgba(255,255,255,0.05)",
              border: "1px solid rgba(255,255,255,0.1)",
              minWidth: "180px",
            }}
          >
            <Search size={14} style={{ color: "rgba(255,255,255,0.3)", flexShrink: 0 }} />
            <input
              type="text"
              value={search}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Search URLs or link text…"
              className="flex-1 bg-transparent outline-none"
              style={{
                fontFamily: "var(--font-poppins), Poppins, sans-serif",
                fontSize: "13px",
                color: "#fff",
                caretColor: "#a855f7",
              }}
            />
            {search && (
              <button onClick={() => onSearchChange("")} className="cursor-pointer">
                <X size={13} style={{ color: "rgba(255,255,255,0.3)" }} />
              </button>
            )}
          </div>

          {/* Sort dropdown */}
          <div ref={sortRef} className="relative">
            <button
              onClick={() => { setSortOpen((p) => !p); setZoneOpen(false); }}
              className="flex items-center gap-2 px-3 py-2 rounded-xl transition-all cursor-pointer"
              style={{
                background: "rgba(255,255,255,0.05)",
                border: "1px solid rgba(255,255,255,0.1)",
                fontFamily: "var(--font-poppins), Poppins, sans-serif",
                fontSize: "13px",
                fontWeight: 500,
                color: "rgba(255,255,255,0.6)",
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
                  background: "rgba(15,8,30,0.97)",
                  backdropFilter: "blur(16px)",
                  border: "1px solid rgba(255,255,255,0.12)",
                  minWidth: "160px",
                  boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
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
                          ? "#e879f9"
                          : "rgba(255,255,255,0.65)",
                      background:
                        sortOption === opt.value
                          ? "rgba(232,121,249,0.08)"
                          : "transparent",
                    }}
                    onMouseEnter={(e) => {
                      if (sortOption !== opt.value)
                        (e.currentTarget as HTMLButtonElement).style.background =
                          "rgba(255,255,255,0.04)";
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
              color: "rgba(255,255,255,0.35)",
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
