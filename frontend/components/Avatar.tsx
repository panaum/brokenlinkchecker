// Circular pastel avatar with a deterministic colour per name — mirrors the
// Deliverables Dashboard's Avatar so the two apps read as one product. The same
// name always resolves to the same tint across the app.
const PALETTE = [
  "bg-[#ece9fb] text-[#5b4fc7]", // violet
  "bg-[#e3edfd] text-[#3b6fd4]", // blue
  "bg-[#fde7ef] text-[#c44d77]", // pink
  "bg-[#fdeede] text-[#bd763a]", // peach
  "bg-[#e1f4ec] text-[#2f9669]", // green
  "bg-[#fbe9e6] text-[#cc5b48]", // coral
  "bg-[#e7f1f6] text-[#3d7c97]", // teal
];

function hash(str: string): number {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) | 0;
  return Math.abs(h);
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

const SIZES = {
  sm: "size-7 text-[11px]",
  md: "size-9 text-[13px]",
  lg: "size-12 text-base",
} as const;

export function Avatar({
  name,
  size = "md",
  className = "",
}: {
  name: string;
  size?: keyof typeof SIZES;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-full font-semibold ${SIZES[size]} ${PALETTE[hash(name) % PALETTE.length]} ${className}`}
      aria-hidden
    >
      {initials(name)}
    </span>
  );
}
