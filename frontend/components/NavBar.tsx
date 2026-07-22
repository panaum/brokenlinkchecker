"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { LayoutDashboard, Link2, Search, Users, Eye } from "lucide-react";
import Image from "next/image";
import AuthButton from "@/components/AuthButton";
import Changelog from "@/components/Changelog";

// Ask the global command palette to open (it listens for this event).
function openPalette() {
  window.dispatchEvent(new CustomEvent("linkspy:open-command-palette"));
}

const NAV_ITEMS = [
  { href: "/", label: "Scanner", icon: Link2 },
  { href: "/scanner", label: "Preview", icon: Eye },
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/clients", label: "Clients", icon: Users },
];

export default function NavBar() {
  const pathname = usePathname();

  return (
    <nav
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 100,
        background: "rgba(255,255,255,0.82)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      <div
        className="max-w-6xl mx-auto px-6 flex items-center justify-between"
        style={{ height: 56 }}
      >
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2 no-underline">
          <Image src="/icon.png" alt="LinkSpy logo" width={30} height={30} style={{ borderRadius: 8 }} />
          <span
            className="font-display"
            style={{
              fontWeight: 800,
              fontSize: "18px",
              color: "var(--text-primary)",
              letterSpacing: "-0.02em",
            }}
          >
            Link<span style={{ color: "var(--signal)" }}>Spy</span>
          </span>
        </Link>

        {/* Nav links */}
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-1">
            {NAV_ITEMS.map((item) => {
              const isActive =
                item.href === "/"
                  ? pathname === "/"
                  : pathname.startsWith(item.href);
              const Icon = item.icon;

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className="relative flex items-center gap-2 px-4 py-2 rounded-lg no-underline transition-colors"
                  style={{
                    fontFamily: "var(--font-poppins), Poppins, sans-serif",
                    fontWeight: 500,
                    fontSize: "13px",
                    color: isActive ? "var(--text-primary)" : "var(--text-muted)",
                    background: isActive ? "rgba(79,70,229,0.06)" : "transparent",
                  }}
                >
                  <Icon size={15} />
                  {item.label}
                  {isActive && (
                    <motion.div
                      layoutId="nav-indicator"
                      className="absolute bottom-0 left-3 right-3"
                      style={{
                        height: 2,
                        borderRadius: 1,
                        background: "var(--signal)",
                      }}
                      transition={{ type: "spring", stiffness: 400, damping: 30 }}
                    />
                  )}
                </Link>
              );
            })}
          </div>

          {/* ⌘K hint — opens the command palette. */}
          <button
            onClick={openPalette}
            aria-label="Open command palette"
            className="hidden sm:flex items-center gap-2"
            style={{
              padding: "6px 10px", borderRadius: 8, cursor: "pointer",
              background: "rgba(28,28,46,0.04)", border: "1px solid var(--border-subtle)",
              color: "var(--text-muted)",
            }}
          >
            <Search size={13} />
            <kbd style={{ fontFamily: "var(--font-stack-mono)", fontSize: 11, letterSpacing: "0.02em" }}>⌘K</kbd>
          </button>

          <Changelog />
          <AuthButton />
        </div>
      </div>
    </nav>
  );
}
