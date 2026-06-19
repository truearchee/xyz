#!/usr/bin/env node
// Stage 4.9d — §8 gate: no inline `style={` on RESTYLED surfaces (§4.4 specificity trap — an inline style
// beats a Tailwind class, so a half-migrated element silently ignores its token classes). Scope = the
// feature/app surfaces restyled in 4.9c. The component library (src/components) is out of scope here: it
// owns ONE sanctioned runtime-dynamic style (the LinearProgress fill width, which can't be a static class).
// The one §5 LEAVE (ModuleDetailView) is ignored with a written reason.
import { readFileSync } from "node:fs";
import { execSync } from "node:child_process";

const SCAN_DIRS = ["src/features", "src/app"];
const IGNORE = [
  // §5 componentize-or-leave: unconsumed, deferred to Stage 12 (see 4.9-restyle-inventory.md).
  "src/features/modules/ModuleDetailView.tsx",
];
// Unconsumed legacy generation (F-4.9-4): depth-1 features/content/*.tsx, barrel-only, superseded by
// features/content/{lecturer,student}/* — LEFT for Stage 12 deletion (§5). The LIVE subdirs are scanned.
const LEGACY_DEAD = /^src\/features\/content\/[^/]+\.tsx$/;
const INLINE = /style=\{/;

const files = execSync(`git ls-files ${SCAN_DIRS.join(" ")}`, { encoding: "utf8" })
  .split("\n")
  .filter((f) => /\.(ts|tsx)$/.test(f) && !IGNORE.includes(f) && !LEGACY_DEAD.test(f));

const violations = [];
for (const file of files) {
  const lines = readFileSync(file, "utf8").split("\n");
  lines.forEach((line, i) => {
    if (INLINE.test(line)) violations.push(`${file}:${i + 1}: ${line.trim()}`);
  });
}

if (violations.length) {
  console.error("check:inline-styles FAILED — inline style={} on a restyled surface (remove it; use token classes):");
  for (const v of violations) console.error("  " + v);
  process.exit(1);
}
console.log(`check:inline-styles OK — ${files.length} restyled feature/app files, no inline style={}.`);
