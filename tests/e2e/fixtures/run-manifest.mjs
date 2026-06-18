import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';

const FIXTURE_DIR = dirname(fileURLToPath(import.meta.url));
export const RUNS_DIR = resolve(FIXTURE_DIR, '..', '.runs');

export const MANIFEST_FIELDS = [
  'authUserIds',
  'appUserIds',
  'moduleIds',
  'sectionIds',
  'membershipIds',
  'assetIds',
  'transcriptIds',
  'transcriptSegmentIds',
  'transcriptChunkIds',
  'ingestionJobIds',
  'aiRequestLogIds',
  'storageKeys',
];

const RUN_ID_PATTERN = /^e2e-[a-z0-9][a-z0-9-]{5,80}$/;

export function createRunId() {
  const suffix = randomUUID().slice(0, 8);
  return `e2e-${Date.now().toString(36)}-${suffix}`;
}

export function assertRunId(runId) {
  if (!RUN_ID_PATTERN.test(runId)) {
    throw new Error(`Invalid E2E run id: ${runId}`);
  }
}

export function ensureRunsDir() {
  mkdirSync(RUNS_DIR, { recursive: true });
}

export function manifestPathForRunId(runId) {
  assertRunId(runId);
  return resolve(RUNS_DIR, `${runId}.json`);
}

export function assertManifestPath(manifestPath) {
  const resolved = resolve(manifestPath);
  const allowedPrefix = `${RUNS_DIR}/`;
  if (!resolved.startsWith(allowedPrefix) || !resolved.endsWith('.json')) {
    throw new Error('Manifest path must live under tests/e2e/.runs/');
  }
  return resolved;
}

export function emptyManifest(runId) {
  assertRunId(runId);
  return {
    runId,
    authUserIds: [],
    appUserIds: [],
    moduleIds: [],
    sectionIds: [],
    membershipIds: [],
    assetIds: [],
    transcriptIds: [],
    transcriptSegmentIds: [],
    transcriptChunkIds: [],
    ingestionJobIds: [],
    aiRequestLogIds: [],
    storageKeys: [],
    createdAt: new Date().toISOString(),
  };
}

export function normalizeManifest(input) {
  assertRunId(input.runId);
  const manifest = {
    ...emptyManifest(input.runId),
    ...input,
  };

  for (const field of MANIFEST_FIELDS) {
    const values = Array.isArray(manifest[field]) ? manifest[field] : [];
    manifest[field] = [...new Set(values.filter(Boolean).map(String))];
  }

  manifest.createdAt = manifest.createdAt || new Date().toISOString();
  return manifest;
}

export function writeManifest(manifest) {
  ensureRunsDir();
  const normalized = normalizeManifest(manifest);
  const path = manifestPathForRunId(normalized.runId);
  writeFileSync(path, `${JSON.stringify(normalized, null, 2)}\n`);
  return { manifest: normalized, path };
}

export function createManifest(runId = createRunId()) {
  return writeManifest(emptyManifest(runId));
}

export function loadManifest(identifier) {
  if (!identifier) {
    throw new Error('Run id or manifest path is required');
  }

  const path = identifier.endsWith('.json')
    ? assertManifestPath(identifier)
    : manifestPathForRunId(identifier);

  if (!existsSync(path)) {
    throw new Error(`Manifest not found: ${path}`);
  }

  const manifest = normalizeManifest(JSON.parse(readFileSync(path, 'utf8')));
  return { manifest, path };
}

export function updateManifest(identifier, updater) {
  const { manifest } = loadManifest(identifier);
  const updated = updater({ ...manifest });
  return writeManifest(updated);
}

export function recordManifestValue(identifier, field, value) {
  if (!MANIFEST_FIELDS.includes(field)) {
    throw new Error(`Unsupported manifest field: ${field}`);
  }

  return updateManifest(identifier, (manifest) => ({
    ...manifest,
    [field]: [...new Set([...(manifest[field] ?? []), String(value)])],
  }));
}

export function recordStorageKey(identifier, storageKey) {
  return recordManifestValue(identifier, 'storageKeys', storageKey);
}

export function recordTranscriptId(identifier, transcriptId) {
  return recordManifestValue(identifier, 'transcriptIds', transcriptId);
}

export function recordAssetId(identifier, assetId) {
  return recordManifestValue(identifier, 'assetIds', assetId);
}
