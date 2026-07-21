// Join conditional class names (truthy strings win). Mirrors the Dashboard's
// `cn` helper without pulling in clsx/tailwind-merge.
export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}
