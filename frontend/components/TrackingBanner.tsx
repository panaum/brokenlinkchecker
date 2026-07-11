"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Bell, Check, Loader2 } from "lucide-react";

interface TrackingBannerProps {
  scannedUrl: string;
  hasHistory: boolean;
}

export default function TrackingBanner({
  scannedUrl,
  hasHistory,
}: TrackingBannerProps) {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Check localStorage to see if already registered for this URL
  useEffect(() => {
    try {
      const stored = localStorage.getItem("linkspy_tracked_urls");
      if (stored) {
        const urls = JSON.parse(stored) as string[];
        if (urls.includes(scannedUrl)) {
          setDismissed(true);
        }
      }
    } catch {
      // Ignore parse errors
    }
  }, [scannedUrl]);

  // Don't show if history exists, already submitted, or dismissed
  if (hasHistory || submitted || dismissed) return null;

  const handleSubmit = async () => {
    if (!email.trim() || !email.includes("@")) {
      setError("Please enter a valid email address");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const res = await fetch("/api/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: scannedUrl, email: email.trim() }),
      });

      if (!res.ok) {
        throw new Error("Registration failed");
      }

      // Save to localStorage
      try {
        const stored = localStorage.getItem("linkspy_tracked_urls");
        const urls: string[] = stored ? (JSON.parse(stored) as string[]) : [];
        if (!urls.includes(scannedUrl)) {
          urls.push(scannedUrl);
        }
        localStorage.setItem("linkspy_tracked_urls", JSON.stringify(urls));
      } catch {
        // Ignore storage errors
      }

      setSubmitted(true);

      // Auto-hide after 3 seconds
      setTimeout(() => setDismissed(true), 3000);
    } catch {
      setError("Failed to register. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="relative z-10 px-4 mb-2">
      <AnimatePresence>
        {!dismissed && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.3 }}
            className="w-full max-w-3xl mx-auto"
          >
            <div
              className="glass-card"
              style={{
                padding: "16px 24px",
                display: "flex",
                flexDirection: "column",
                gap: 12,
              }}
            >
              {/* Header */}
              <div className="flex items-center gap-3">
                <div
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: 10,
                    background:
                      "linear-gradient(132deg, rgb(23,184,148), rgb(52,230,192))",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                  }}
                >
                  <Bell size={18} style={{ color: "white" }} />
                </div>
                <div>
                  <p
                    style={{
                      fontFamily: "var(--font-poppins), Poppins, sans-serif",
                      fontWeight: 600,
                      fontSize: "14px",
                      color: "white",
                      margin: 0,
                      lineHeight: 1.4,
                    }}
                  >
                    🔔 Want to track this site over time?
                  </p>
                  <p
                    style={{
                      fontFamily: "var(--font-poppins), Poppins, sans-serif",
                      fontWeight: 400,
                      fontSize: "12px",
                      color: "rgba(255,255,255,0.55)",
                      margin: 0,
                      lineHeight: 1.4,
                    }}
                  >
                    Enter your email to save scan history and get alerts when new
                    issues appear.
                  </p>
                </div>
              </div>

              {/* Input + Button */}
              {!submitted ? (
                <div className="flex items-center gap-2 flex-wrap">
                  <input
                    type="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleSubmit();
                    }}
                    style={{
                      flex: 1,
                      minWidth: 200,
                      padding: "8px 14px",
                      borderRadius: 8,
                      border: "1px solid rgba(255,255,255,0.12)",
                      background: "rgba(255,255,255,0.05)",
                      color: "white",
                      fontFamily: "var(--font-poppins), Poppins, sans-serif",
                      fontSize: "13px",
                      outline: "none",
                    }}
                  />
                  <button
                    onClick={handleSubmit}
                    disabled={submitting}
                    style={{
                      padding: "8px 20px",
                      borderRadius: 8,
                      background:
                        "linear-gradient(132deg, rgb(23,184,148), rgb(52,230,192))",
                      color: "white",
                      fontFamily: "var(--font-poppins), Poppins, sans-serif",
                      fontWeight: 600,
                      fontSize: "13px",
                      border: "none",
                      cursor: submitting ? "not-allowed" : "pointer",
                      opacity: submitting ? 0.7 : 1,
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      transition: "opacity 0.2s",
                    }}
                  >
                    {submitting ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : null}
                    Start Tracking
                  </button>
                  {error && (
                    <p
                      style={{
                        fontFamily:
                          "var(--font-poppins), Poppins, sans-serif",
                        fontSize: "12px",
                        color: "#f87171",
                        margin: 0,
                        width: "100%",
                      }}
                    >
                      {error}
                    </p>
                  )}
                </div>
              ) : (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="flex items-center gap-2"
                >
                  <Check size={16} style={{ color: "#4ade80" }} />
                  <span
                    style={{
                      fontFamily: "var(--font-poppins), Poppins, sans-serif",
                      fontSize: "13px",
                      fontWeight: 500,
                      color: "#4ade80",
                    }}
                  >
                    Tracking started! We&apos;ll remember every scan for{" "}
                    {scannedUrl}
                  </span>
                </motion.div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
