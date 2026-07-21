"use client";

import { motion } from "framer-motion";
import { Globe, FileSearch, Link2, ShieldCheck, Check, X } from "lucide-react";

interface ScanProgressProps {
  message: string;
  percent: number;
  checkedCount?: number;
  totalCount?: number;
  // Accepted for compatibility with the caller; the stepper doesn't render it.
  feed?: string[];
  onCancel?: () => void;
}

const STEPS = [
  { label: "Launching Browser", icon: Globe },
  { label: "Reading Page", icon: FileSearch },
  { label: "Extracting Links", icon: Link2 },
  { label: "Checking Each Link", icon: ShieldCheck },
] as const;

function getStepIndex(percent: number): number {
  if (percent < 15) return 0;
  if (percent < 30) return 1;
  if (percent < 50) return 2;
  return 3;
}

export default function ScanProgress({
  message,
  percent,
  checkedCount,
  totalCount,
  onCancel,
}: ScanProgressProps) {
  const currentStep = getStepIndex(percent);

  const estimatedSecsLeft =
    totalCount && checkedCount && checkedCount > 0 && percent < 100
      ? Math.ceil(
          ((totalCount - checkedCount) / checkedCount) *
            (percent / 100) *
            30
        )
      : null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      className="w-full max-w-3xl mx-auto mt-4 relative z-10"
    >
      <div className="glass-panel p-6 flex flex-col gap-5">
        {/* Stepper */}
        <div className="flex items-center justify-between gap-2">
          {STEPS.map((step, i) => {
            const Icon = step.icon;
            const isDone = i < currentStep;
            const isCurrent = i === currentStep;
            return (
              <div key={step.label} className="flex flex-col items-center gap-1.5 flex-1">
                {/* Circle */}
                <div
                  className="relative flex items-center justify-center rounded-full"
                  style={{
                    width: 36,
                    height: 36,
                    background: isDone
                      ? "rgba(76,175,125,0.15)"
                      : isCurrent
                      ? "var(--signal)"
                      : "rgba(28,28,46,0.04)",
                    border: isDone
                      ? "1.5px solid var(--status-healthy)"
                      : isCurrent
                      ? "1.5px solid rgba(79,70,229,0.8)"
                      : "1.5px solid var(--border-subtle)",
                    boxShadow: isCurrent
                      ? "0 0 12px rgba(79,70,229,0.4)"
                      : "none",
                  }}
                >
                  {isCurrent && (
                    <span
                      className="absolute inset-0 rounded-full animate-ping"
                      style={{
                        background:
                          "var(--signal)",
                        opacity: 0.25,
                      }}
                    />
                  )}
                  {isDone ? (
                    <Check size={16} color="var(--status-healthy)" />
                  ) : (
                    <Icon
                      size={16}
                      color={
                        isCurrent ? "#fff" : "var(--text-muted)"
                      }
                    />
                  )}
                </div>
                {/* Label */}
                <span
                  style={{
                    fontFamily: "var(--font-poppins), Poppins, sans-serif",
                    fontSize: "11px",
                    fontWeight: isCurrent ? 600 : 400,
                    color: isDone
                      ? "var(--status-healthy)"
                      : isCurrent
                      ? "var(--text-primary)"
                      : "var(--text-muted)",
                    textDecoration: isDone ? "line-through" : "none",
                    textAlign: "center",
                  }}
                >
                  {step.label}
                </span>
              </div>
            );
          })}
        </div>

        {/* Connector line */}
        <div className="relative flex items-center -mt-3 px-5">
          <div className="h-px flex-1 bg-[var(--border-subtle)]" />
          <div
            className="absolute left-5 h-px bg-[var(--signal)] transition-all duration-700"
            style={{ width: `${(currentStep / (STEPS.length - 1)) * 100}%` }}
          />
        </div>

        {/* Message + counter */}
        <div className="flex items-center justify-between gap-4">
          <span
            style={{
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              fontSize: "13px",
              fontWeight: 400,
              color: "var(--text-secondary)",
              flexShrink: 1,
              minWidth: 0,
            }}
          >
            {message}
          </span>
          {checkedCount !== undefined && totalCount !== undefined && totalCount > 0 && (
            <span
              style={{
                fontFamily: "var(--font-poppins), Poppins, sans-serif",
                fontSize: "16px",
                fontWeight: 700,
                color: "var(--text-primary)",
                whiteSpace: "nowrap",
                tabularNums: true,
              } as React.CSSProperties}
            >
              {checkedCount} / {totalCount}
            </span>
          )}
        </div>

        {/* Progress bar */}
        <div className="w-full h-2 rounded-full bg-[var(--border-subtle)] overflow-hidden">
          <div
            className="h-full rounded-full bg-[var(--signal)] progress-fill"
            style={{ width: `${percent}%` }}
          />
        </div>

        {/* ETA + Cancel */}
        <div className="flex items-center justify-between">
          <span
            style={{
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              fontSize: "12px",
              color: "var(--text-muted)",
            }}
          >
            {estimatedSecsLeft !== null
              ? `~${estimatedSecsLeft}s remaining`
              : "Calculating…"}
          </span>
          {onCancel && (
            <button
              onClick={onCancel}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg transition-all cursor-pointer"
              style={{
                fontFamily: "var(--font-poppins), Poppins, sans-serif",
                fontSize: "12px",
                fontWeight: 500,
                color: "var(--text-muted)",
                background: "rgba(28,28,46,0.04)",
                border: "1px solid var(--border-subtle)",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.color = "var(--status-broken)";
                (e.currentTarget as HTMLButtonElement).style.borderColor =
                  "rgba(224,92,92,0.3)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.color =
                  "var(--text-muted)";
                (e.currentTarget as HTMLButtonElement).style.borderColor =
                  "var(--border-subtle)";
              }}
            >
              <X size={13} />
              Cancel
            </button>
          )}
        </div>
      </div>
    </motion.div>
  );
}
