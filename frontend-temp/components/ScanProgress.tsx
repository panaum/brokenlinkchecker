"use client";

import { motion } from "framer-motion";
import { Globe, FileSearch, Link2, ShieldCheck, Check, X } from "lucide-react";

interface ScanProgressProps {
  message: string;
  percent: number;
  checkedCount?: number;
  totalCount?: number;
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
      className="w-full max-w-3xl mx-auto mt-4 px-4"
    >
      <div className="glass-card p-6 flex flex-col gap-5">
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
                      ? "rgba(76,175,125,0.12)"
                      : isCurrent
                      ? "var(--color-accent)"
                      : "var(--color-card-soft)",
                    border: isDone
                      ? "1.5px solid var(--color-success)"
                      : isCurrent
                      ? "1.5px solid var(--color-accent)"
                      : "1.5px solid var(--color-border-soft)",
                    boxShadow: isCurrent
                      ? "0 0 0 4px rgba(79,70,229,0.15)"
                      : "none",
                  }}
                >
                  {isCurrent && (
                    <span
                      className="absolute inset-0 rounded-full animate-ping"
                      style={{
                        background: "var(--color-accent)",
                        opacity: 0.2,
                      }}
                    />
                  )}
                  {isDone ? (
                    <Check size={16} color="var(--color-success)" />
                  ) : (
                    <Icon
                      size={16}
                      color={isCurrent ? "#fff" : "var(--color-text-muted)"}
                    />
                  )}
                </div>
                {/* Label */}
                <span
                  style={{
                    fontSize: "11px",
                    fontWeight: isCurrent ? 600 : 400,
                    color: isDone
                      ? "var(--color-success)"
                      : isCurrent
                      ? "var(--color-text-primary)"
                      : "var(--color-text-muted)",
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
          <div className="h-px flex-1 bg-border-soft" />
          <div
            className="absolute left-5 h-px bg-accent transition-all duration-700"
            style={{ width: `${(currentStep / (STEPS.length - 1)) * 100}%` }}
          />
        </div>

        {/* Message + counter */}
        <div className="flex items-center justify-between gap-4">
          <span
            className="text-text-secondary"
            style={{ fontSize: "13px", flexShrink: 1, minWidth: 0 }}
          >
            {message}
          </span>
          {checkedCount !== undefined && totalCount !== undefined && totalCount > 0 && (
            <span
              className="text-text-primary tabular-nums"
              style={{ fontSize: "16px", fontWeight: 700, whiteSpace: "nowrap" }}
            >
              {checkedCount} / {totalCount}
            </span>
          )}
        </div>

        {/* Progress bar */}
        <div className="w-full h-2 rounded-full bg-card-soft overflow-hidden">
          <div
            className="h-full rounded-full bg-accent progress-fill"
            style={{ width: `${percent}%` }}
          />
        </div>

        {/* ETA + Cancel */}
        <div className="flex items-center justify-between">
          <span className="text-text-muted" style={{ fontSize: "12px" }}>
            {estimatedSecsLeft !== null
              ? `~${estimatedSecsLeft}s remaining`
              : "Calculating…"}
          </span>
          {onCancel && (
            <button
              onClick={onCancel}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg transition-all cursor-pointer"
              style={{
                fontSize: "12px",
                fontWeight: 500,
                color: "var(--color-text-secondary)",
                background: "var(--color-card)",
                border: "1px solid var(--color-border-soft)",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.color = "var(--color-error)";
                (e.currentTarget as HTMLButtonElement).style.borderColor =
                  "rgba(224,92,92,0.4)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.color =
                  "var(--color-text-secondary)";
                (e.currentTarget as HTMLButtonElement).style.borderColor =
                  "var(--color-border-soft)";
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
