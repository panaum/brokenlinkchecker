import type { Metadata } from "next";
import { Poppins } from "next/font/google";
import "./globals.css";

const poppins = Poppins({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  display: "swap",
  variable: "--font-poppins",
});

export const metadata: Metadata = {
  title: "LinkSpy — Broken Link Checker",
  description:
    "Instantly scan any webpage for broken links across nav, header, footer, CTAs, and body text.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={poppins.variable} suppressHydrationWarning>
      <body className={`${poppins.className} bg-[#0a0612] antialiased`} suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
