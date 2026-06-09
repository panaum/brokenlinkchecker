"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { Link2, LayoutDashboard } from "lucide-react";
import AuthButton from "@/components/AuthButton";

const NAV_ITEMS = [
  { href: "/", label: "Scanner", icon: Link2 },
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
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
        background: "rgba(10,6,18,0.85)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        borderBottom: "1px solid rgba(255,255,255,0.06)",
      }}
    >
      <div
        className="max-w-6xl mx-auto px-6 flex items-center justify-between"
        style={{ height: 56 }}
      >
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2 no-underline">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{
              background: "linear-gradient(132deg, rgb(65,0,153), rgb(138,26,155))",
            }}
          >
            <Link2 size={16} style={{ color: "#fff" }} />
          </div>
          <span
            style={{
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              fontWeight: 700,
              fontSize: "18px",
              color: "#fff",
            }}
          >
            Link<span style={{ color: "rgba(255,255,255,0.5)" }}>Spy</span>
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
                    color: isActive ? "#fff" : "rgba(255,255,255,0.45)",
                    background: isActive ? "rgba(255,255,255,0.06)" : "transparent",
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
                        background: "linear-gradient(90deg, rgb(138,26,155), rgb(200,100,255))",
                      }}
                      transition={{ type: "spring", stiffness: 400, damping: 30 }}
                    />
                  )}
                </Link>
              );
            })}
          </div>

          <AuthButton />
        </div>
      </div>
    </nav>
  );
}
