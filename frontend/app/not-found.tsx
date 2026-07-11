import Link from "next/link";

export default function NotFound() {
  return (
    <main style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
      <div style={{ textAlign: "center", maxWidth: 420 }}>
        <div className="font-mono ds-text-muted" style={{ fontSize: 13, letterSpacing: "0.1em" }}>404</div>
        <h1 className="font-display ds-text-primary" style={{ fontSize: "var(--text-display)", fontWeight: 700, marginTop: 8 }}>
          This page is broken. Ironic.
        </h1>
        <p className="ds-text-secondary" style={{ fontSize: "var(--text-body)", marginTop: 10 }}>
          The link you followed doesn&apos;t lead anywhere — exactly the kind of thing LinkSpy catches.
        </p>
        <Link href="/" className="ds-btn-primary" style={{ display: "inline-flex", marginTop: 24, textDecoration: "none" }}>
          Scan your site instead
        </Link>
      </div>
    </main>
  );
}
