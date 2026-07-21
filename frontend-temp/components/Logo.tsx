// Apexure mark — two inward-pointing chevrons (violet + indigo). Shared with
// the Deliverables Dashboard so the two apps read as one product.
export function Logo({ className = "size-6" }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" fill="none" className={className} aria-hidden>
      <path
        d="M14 11 L22 24 L14 37"
        stroke="#7c3aed"
        strokeWidth="6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M34 11 L26 24 L34 37"
        stroke="#312e81"
        strokeWidth="6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
