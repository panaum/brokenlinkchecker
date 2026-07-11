import type { Metadata } from "next";
import { Bricolage_Grotesque, Familjen_Grotesk, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import Providers from "@/components/SessionProvider";
import CommandPalette from "@/components/CommandPalette";

// Identity typography, self-hosted via next/font.
//  - display: Bricolage Grotesque — technical-editorial, high-personality, for
//    headings and verdicts.
//  - body:    Familjen Grotesk — a warm grotesk, readable at body sizes.
//  - mono:    JetBrains Mono — every piece of DATA (URLs, scores, counts,
//    timestamps, status codes) with tabular numerals. Data in mono is what
//    makes an instrument read as an instrument.
const display = Bricolage_Grotesque({
  subsets: ["latin"],
  weight: ["500", "600", "700", "800"],
  display: "swap",
  variable: "--font-display",
});

const body = Familjen_Grotesk({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--font-body",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--font-mono",
});

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
      className={`${display.variable} ${body.variable} ${mono.variable}`}
      suppressHydrationWarning
    >
      <head>
        {/* Set the theme before paint so there's no flash of the wrong theme. */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "(function(){try{var t=localStorage.getItem('linkspy:theme');document.documentElement.setAttribute('data-theme',t==='light'?'light':'dark');}catch(e){document.documentElement.setAttribute('data-theme','dark');}})();",
          }}
        />
      </head>
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
