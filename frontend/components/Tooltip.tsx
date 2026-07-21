"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";

interface TooltipProps {
  content: string;
  children: React.ReactNode;
}

export default function Tooltip({ content, children }: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const [pos, setPos] = useState<"top" | "bottom">("top");
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (visible && wrapRef.current) {
      const rect = wrapRef.current.getBoundingClientRect();
      setPos(rect.top < 120 ? "bottom" : "top");
    }
  }, [visible]);

  return (
    <div
      ref={wrapRef}
      className="relative inline-flex items-center"
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
    >
      {children}
      <AnimatePresence>
        {visible && (
          <motion.div
            initial={{ opacity: 0, y: pos === "top" ? 4 : -4, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: pos === "top" ? 4 : -4, scale: 0.96 }}
            transition={{ duration: 0.15 }}
            className="absolute z-50 pointer-events-none"
            style={{
              ...(pos === "top"
                ? { bottom: "calc(100% + 8px)" }
                : { top: "calc(100% + 8px)" }),
              left: "50%",
              transform: "translateX(-50%)",
              width: "220px",
            }}
          >
            <div
              style={{
                background: "var(--text-primary)",
                border: "1px solid var(--text-primary)",
                borderRadius: "10px",
                padding: "8px 12px",
                fontSize: "12px",
                lineHeight: "1.5",
                color: "#fff",
                fontFamily: "var(--font-poppins), Poppins, sans-serif",
                fontWeight: 400,
              }}
            >
              {content}
            </div>
            {/* Arrow */}
            <div
              style={{
                position: "absolute",
                ...(pos === "top"
                  ? { top: "100%", borderBottom: "none" }
                  : { bottom: "100%", borderTop: "none" }),
                left: "50%",
                transform: "translateX(-50%)",
                width: 0,
                height: 0,
                borderLeft: "6px solid transparent",
                borderRight: "6px solid transparent",
                ...(pos === "top"
                  ? { borderTop: "6px solid var(--text-primary)" }
                  : { borderBottom: "6px solid var(--text-primary)" }),
              }}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
