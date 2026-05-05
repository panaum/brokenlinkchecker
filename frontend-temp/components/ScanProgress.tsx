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
      className="w-full max-w-3xl mx-auto mt-4"
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
                      ? "rgba(74,222,128,0.15)"
                      : isCurrent
                      ? "linear-gradient(132deg,rgb(65,0,153),rgb(138,26,155))"
                      : "rgba(255,255,255,0.05)",
                    border: isDone
                      ? "1.5px solid #4ade80"
                      : isCurrent
                      ? "1.5px solid rgba(138,26,155,0.8)"
                      : "1.5px solid rgba(255,255,255,0.1)",
                    boxShadow: isCurrent
                      ? "0 0 12px rgba(138,26,155,0.5)"
                      : "none",
                  }}
                >
                  {isCurrent && (
                    <span
                      className="absolute inset-0 rounded-full animate-ping"
                      style={{
                        background:
                          "linear-gradient(132deg,rgb(65,0,153),rgb(138,26,155))",
                        opacity: 0.25,
                      }}
                    />
                  )}
                  {isDone ? (
                    <Check size={16} color="#4ade80" />
                  ) : (
                    <Icon
                      size={16}
                      color={
                        isCurrent ? "#fff" : "rgba(255,255,255,0.3)"
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
                      ? "#4ade80"
                      : isCurrent
                      ? "#fff"
                      : "rgba(255,255,255,0.3)",
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
          <div className="h-px flex-1 bg-white/10" />
          <div
            className="absolute left-5 h-px bg-gradient-to-r from-purple-600 to-fuchsia-600 transition-all duration-700"
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
              color: "rgba(255,255,255,0.65)",
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
                color: "#fff",
                whiteSpace: "nowrap",
                tabularNums: true,
              } as React.CSSProperties}
            >
              {checkedCount} / {totalCount}
            </span>
          )}
        </div>

        {/* Progress bar */}
        <div className="w-full h-2 rounded-full bg-white/10 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-1 progress-fill"
            style={{ width: `${percent}%` }}
          />
        </div>

        {/* ETA + Cancel */}
        <div className="flex items-center justify-between">
          <span
            style={{
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              fontSize: "12px",
              color: "rgba(255,255,255,0.35)",
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
                color: "rgba(255,255,255,0.5)",
                background: "rgba(255,255,255,0.05)",
                border: "1px solid rgba(255,255,255,0.1)",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.color = "#f87171";
                (e.currentTarget as HTMLButtonElement).style.borderColor =
                  "rgba(248,113,113,0.3)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.color =
                  "rgba(255,255,255,0.5)";
                (e.currentTarget as HTMLButtonElement).style.borderColor =
                  "rgba(255,255,255,0.1)";
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
