"use client";

import React, { useEffect, useState } from "react";
import { Sun, Moon } from "lucide-react";

const KEY = "linkspy:theme";

// Toggles the app between dark (default) and light. The initial value is set
// before paint by an inline script in the layout, so there's no flash; this
// just reflects and updates it.
export default function ThemeToggle() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const current = (document.documentElement.getAttribute("data-theme") as "dark" | "light") || "dark";
    setTheme(current);
  }, []);

  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem(KEY, next); } catch { /* ignore */ }
  };

  return (
    <button
      onClick={toggle}
      aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
      title={theme === "dark" ? "Light theme" : "Dark theme"}
      style={{ display: "flex", alignItems: "center", padding: 8, borderRadius: 8, cursor: "pointer", background: "none", border: "none", color: "var(--text-muted)" }}
    >
      {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}
