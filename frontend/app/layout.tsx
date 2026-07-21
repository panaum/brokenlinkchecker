import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";
import Providers from "@/components/SessionProvider";
import CommandPalette from "@/components/CommandPalette";

// Typography — Geist, matched to the Deliverables Dashboard so the two apps
// read as one product. Sans carries UI + headings; mono carries every piece of
// DATA (URLs, scores, counts, timestamps, status codes) with tabular numerals.

export const metadata: Metadata = {
  title: "LinkSpy — Broken Link Checker",
  description:
    "Instantly scan any webpage for broken links across nav, header, footer, CTAs, and body text.",
  openGraph: {
    title: "LinkSpy — Broken Link Checker",
    description:
      "Instantly scan any webpage for broken links across nav, header, footer, CTAs, and body text.",
    type: "website",
    locale: "en_US",
    siteName: "LinkSpy",
  },
  twitter: {
    card: "summary_large_image",
    title: "LinkSpy — Broken Link Checker",
    description:
      "Instantly scan any webpage for broken links across nav, header, footer, CTAs, and body text.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${GeistSans.variable} ${GeistMono.variable}`}
      suppressHydrationWarning
    >
      <body className="antialiased" suppressHydrationWarning>
        <Providers>
          {children}
          {/* Global ⌘K command palette — reachable from every page. */}
          <CommandPalette />
        </Providers>
      </body>
    </html>
  );
}
