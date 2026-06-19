#!/usr/bin/env node
// Stage 4.9d — §8 gate: no raw hex / off-token colour values in component or restyled-surface source.
// Components + restyled surfaces reference SEMANTIC TOKENS only (§4.1/§4.4). Generated client + the
// upload.ts exception + fonts are out of scope. The one §5 LEAVE (ModuleDetailView) is ignored with a
// written reason (it is the Stage-12 backlog surface, deliberately not restyled).
import { readFileSync } from "node:fs";
import { execSync } from "node:child_process";

const SCAN_DIRS = ["src/components", "src/features", "src/app"];
const IGNORE = [
  // §5 componentize-or-leave: unconsumed, deferred to Stage 12 (see 4.9-restyle-inventory.md).
  "src/features/modules/ModuleDetailView.tsx",
];
// Unconsumed legacy generation (F-4.9-4): the depth-1 features/content/*.tsx components are barrel-only,
// superseded by features/content/{lecturer,student}/* — LEFT for Stage 12 deletion (§5). Excluded here;
// the LIVE lecturer/ + student/ subdirs are still scanned.
const LEGACY_DEAD = /^src\/features\/content\/[^/]+\.tsx$/;
const HEX = /#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b/;

const files = execSync(`git ls-files ${SCAN_DIRS.join(" ")}`, { encoding: "utf8" })
  .split("\n")
  .filter((f) => /\.(ts|tsx|css)$/.test(f) && !IGNORE.includes(f) && !LEGACY_DEAD.test(f));

const violations = [];
for (const file of files) {
  const lines = readFileSync(file, "utf8").split("\n");
  lines.forEach((line, i) => {
    // globals.css IS the token source (the only place raw palette hex is allowed to live).
    if (file.endsWith("globals.css")) return;
    if (HEX.test(line)) violations.push(`${file}:${i + 1}: ${line.trim()}`);
  });
}

if (violations.length) {
  console.error("check:design-tokens FAILED — raw hex in component/restyled source (use semantic tokens):");
  for (const v of violations) console.error("  " + v);
  process.exit(1);
}
console.log(`check:design-tokens OK — ${files.length} files, no raw hex outside globals.css.`);
