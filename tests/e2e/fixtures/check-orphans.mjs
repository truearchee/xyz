#!/usr/bin/env node
// Stage 4.9e §7.4 (F-4.9-2 prevention) — PRE-RUN orphan check. Counts course_modules owned by
// e2e-domain users (@xyz-lms-e2e.dev / @example.test). A clean DB has ZERO of these (the standing seed
// users own no modules until a run creates them, and teardown removes them). So any found here = orphans
// a prior run failed to tear down — the accumulation that broke the Phase-0 baseline (F-4.9-1). FAIL LOUD
// so it is caught at the START of a run, never discovered as a mid-suite flake.
import { spawnSync } from "node:child_process";

// Exclude the seed's STANDING fixture module ('e2e_module', a fixed-id upsert owned by lecturer_e2e@…
// that the runId-scoped teardown intentionally leaves — it is legitimate, not debris). Any OTHER
// e2e-owned module is a test-created leftover = orphan (the F-4.9-1 accumulation: "Module A …", "Checkpoint
// Smoke …" owned by run-scoped owner_*@xyz-lms-e2e.dev users).
const SQL =
  "SELECT count(*) FROM course_modules WHERE title <> 'e2e_module' AND owner_id IN " +
  "(SELECT id FROM app_users WHERE email LIKE '%@xyz-lms-e2e.dev' OR email LIKE '%@example.test');";

const result = spawnSync(
  "docker",
  ["compose", "exec", "-T", "db", "psql", "-tA", "-U", "postgres", "-d", "xyz_lms", "-c", SQL],
  { encoding: "utf8" },
);

if (result.status !== 0) {
  console.error("check-orphans: psql failed —", (result.stderr || result.stdout || "").trim());
  process.exit(2);
}

const count = Number.parseInt(result.stdout.trim(), 10);
if (Number.isNaN(count)) {
  console.error("check-orphans: could not parse count from:", result.stdout);
  process.exit(2);
}

if (count > 0) {
  console.error(
    `check-orphans FAILED — ${count} orphaned e2e-owned course_modules left by a prior run ` +
      "(teardown skipped). Purge before running the suite (see 4.9-baseline.md / F-4.9-1).",
  );
  process.exit(1);
}

console.log("check-orphans OK — no orphaned e2e-owned course_modules.");
