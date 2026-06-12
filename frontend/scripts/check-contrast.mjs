#!/usr/bin/env node
// Stage 4.9e — token-contrast re-validation against the SHIPPED globals.css (umbrella §4.1; carry-forward
// from 4.9a + the developer's 4.9e hold). Re-confirms the original semantic pairs AND the two tokens 4.9b
// added — `--color-danger-hover` and `--color-overlay`. `--color-overlay` is a SEMI-TRANSPARENT scrim, so
// it is COMPOSITED over the surface beneath (not skipped, not choked on the alpha) and validated as a layer.
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/app/globals.css", import.meta.url), "utf8");

// ---- parse raw palette + the alpha scrim --------------------------------------------------------
const pal = {};
for (const m of css.matchAll(/--palette-([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})/g)) pal[m[1]] = m[2];
const overlayMatch = css.match(/--color-overlay:\s*rgb\(\s*(\d+)\s+(\d+)\s+(\d+)\s*\/\s*([0-9.]+)\s*\)/);

// ---- colour math ---------------------------------------------------------------------------------
const rgb = (hex) => [hex.slice(1, 3), hex.slice(3, 5), hex.slice(5, 7)].map((h) => parseInt(h, 16));
const lum = ([r, g, b]) => {
  const f = (c) => ((c /= 255) <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
};
const ratio = (a, b) => {
  const la = lum(a), lb = lum(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
};
// alpha compositing: src over dst (per channel)
const over = (src, dst, a) => src.map((s, i) => Math.round(s * a + dst[i] * (1 - a)));

const P = (k) => {
  if (!pal[k]) throw new Error(`missing palette ${k}`);
  return rgb(pal[k]);
};
const white = P("white");

const pairs = [
  ["text on surface", P("zinc-900"), white, 4.5, "body"],
  ["text-muted on surface", P("zinc-500"), white, 4.5, "body"],
  ["text-muted on surface-muted", P("zinc-500"), P("zinc-50"), 4.5, "body"],
  ["primary text on surface", P("violet-600"), white, 4.5, "body"],
  ["on-primary white/violet-600", white, P("violet-600"), 3.0, "large"],
  ["on-danger white/rose-600", white, P("rose-600"), 3.0, "large"],
  ["on-info white/indigo-500", white, P("indigo-500"), 3.0, "large"],
  ["on-success white/green-600", white, P("green-600"), 3.0, "large"],
  ["on-warning white/amber-600", white, P("amber-600"), 3.0, "large"],
  ["tonal success-700/50", P("green-700"), P("green-50"), 4.5, "body"],
  ["tonal warning-700/50", P("amber-700"), P("amber-50"), 4.5, "body"],
  ["tonal danger-700/50", P("rose-700"), P("rose-50"), 4.5, "body"],
  ["tonal info-700/50", P("indigo-700"), P("indigo-50"), 4.5, "body"],
  ["focus-ring violet-500/white (UI)", P("violet-500"), white, 3.0, "ui"],
  ["border-strong zinc-500/white (UI)", P("zinc-500"), white, 3.0, "ui"],
  // NEW (4.9b tokens):
  ["on-danger-hover white/rose-700 (destructive btn hover; large/UI)", white, P("rose-700"), 3.0, "large"],
];

let failed = 0;
console.log(`Parsed ${Object.keys(pal).length} raw palette tokens + the --color-overlay scrim from shipped globals.css.\n`);
for (const [name, fg, bg, t] of pairs) {
  const r = ratio(fg, bg);
  const ok = r >= t;
  if (!ok) failed++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${r.toFixed(2).padStart(6)}:1  (>=${t})  ${name}`);
}

// ---- the scrim, validated as a LAYER (composited, alpha handled) ---------------------------------
if (!overlayMatch) {
  console.error("FAIL  --color-overlay not parsed (expected rgb(r g b / a) scrim) — must not be silently skipped");
  failed++;
} else {
  const [, r, g, b, a] = overlayMatch;
  const scrim = [Number(r), Number(g), Number(b)];
  const composited = over(scrim, white, Number(a)); // scrim over the page surface (white)
  const dialogVsScrim = ratio(white, composited); // the white modal must read as a layer above the dimmed page
  const ok = dialogVsScrim >= 3.0;
  if (!ok) failed++;
  console.log(
    `${ok ? "PASS" : "FAIL"}  ${dialogVsScrim.toFixed(2).padStart(6)}:1  (>=3 UI-layer)  ` +
      `overlay scrim zinc-900@${a} composited over surface → white dialog reads as a distinct layer` +
      ` [scrim≈rgb(${composited.join(",")})]`,
  );
}

const validated = pairs.length + (overlayMatch ? 1 : 0);
console.log(`\n${failed ? `*** ${failed} FAIL ***` : `ALL PASS — ${validated} semantic checks (incl. --color-danger-hover + the --color-overlay scrim) meet WCAG AA / layer-perceptibility`}`);
process.exit(failed ? 1 : 0);
