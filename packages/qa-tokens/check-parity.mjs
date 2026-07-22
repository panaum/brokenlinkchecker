/*
 * Parity guard: tokens.css and tokens.ts must carry the same palette.
 *
 * Both files hand-list the same hex values (CSS for runtime, TS for typed use).
 * If someone edits one and forgets the other, colours silently diverge across
 * the three apps. This fails the build the moment they disagree.
 *
 * Framework-free on purpose — `node check-parity.mjs`, exit 1 on mismatch.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const hexes = (file) => {
  const text = readFileSync(join(here, file), "utf8");
  return new Set((text.match(/#[0-9a-fA-F]{6}\b/g) || []).map((h) => h.toUpperCase()));
};

const css = hexes("tokens.css");
const ts = hexes("tokens.ts");

const onlyCss = [...css].filter((h) => !ts.has(h)).sort();
const onlyTs = [...ts].filter((h) => !css.has(h)).sort();

if (onlyCss.length || onlyTs.length) {
  console.error("✗ token parity FAILED — tokens.css and tokens.ts disagree:");
  if (onlyCss.length) console.error("  only in tokens.css:", onlyCss.join(", "));
  if (onlyTs.length) console.error("  only in tokens.ts: ", onlyTs.join(", "));
  process.exit(1);
}

console.log(`✓ token parity OK — ${css.size} hex values match across tokens.css / tokens.ts`);
