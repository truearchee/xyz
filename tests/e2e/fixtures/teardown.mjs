#!/usr/bin/env node

import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import {
  loadManifest,
  MANIFEST_FIELDS,
} from './run-manifest.mjs';

const ENV_PATH = resolve(process.cwd(), '.env.e2e');
const APP_DATABASE_SERVICE = 'db';
const APP_DATABASE_NAME = 'xyz_lms';
const APP_DATABASE_USER = 'postgres';
const E2E_ACTOR_DOMAIN = 'xyz-lms-e2e.dev';
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const ASSET_STORAGE_KEY_PATTERN =
  /^modules\/[0-9a-f-]{36}\/sections\/[0-9a-f-]{36}\/assets\/[0-9a-f-]{36}\/[^/]+\.(pdf|ipynb)$/i;
const TRANSCRIPT_STORAGE_KEY_PATTERN =
  /^modules\/[0-9a-f-]{36}\/sections\/[0-9a-f-]{36}\/transcripts\/[0-9a-f-]{36}\/[^/]+$/i;
const LEGACY_DIRECT_TRANSCRIPT_STORAGE_KEY_PATTERN =
  /^modules\/[0-9a-f-]{36}\/sections\/\d+\/[0-9a-f-]{36}\.vtt$/i;

function loadEnv() {
  if (!existsSync(ENV_PATH)) {
    throw new Error('.env.e2e is required before E2E teardown');
  }

  const parsed = {};
  const lines = readFileSync(ENV_PATH, 'utf8').split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) {
      continue;
    }
    const separator = trimmed.indexOf('=');
    if (separator === -1) {
      continue;
    }
    const key = trimmed.slice(0, separator).trim();
    const value = trimmed.slice(separator + 1).trim().replace(/^"(.*)"$/, '$1');
    parsed[key] = value;
  }

  return { ...parsed, ...process.env };
}

function requireEnv(env, names) {
  const missing = names.filter((name) => !env[name]);
  if (missing.length > 0) {
    throw new Error(`Missing required .env.e2e variables: ${missing.join(', ')}`);
  }
}

function assertAllowedSupabaseUrl(env) {
  const supabaseUrl = new URL(env.NEXT_PUBLIC_SUPABASE_URL);
  const allowedUrl = new URL(env.E2E_SUPABASE_ALLOWED_URL);

  if (supabaseUrl.href !== allowedUrl.href) {
    throw new Error('NEXT_PUBLIC_SUPABASE_URL must exactly match E2E_SUPABASE_ALLOWED_URL');
  }

  const isLocal =
    ['localhost', '127.0.0.1'].includes(supabaseUrl.hostname) &&
    supabaseUrl.port === '54321';
  const isDedicatedE2E =
    supabaseUrl.protocol === 'https:' &&
    supabaseUrl.hostname.endsWith('.supabase.co');

  if (!isLocal && !isDedicatedE2E) {
    throw new Error(
      'E2E Supabase URL must be local Supabase or an exact dedicated Supabase project URL',
    );
  }

  if (!isLocal && env.E2E_DESTRUCTIVE_TARGET_CONFIRM !== 'dedicated-e2e-supabase') {
    throw new Error(
      'Remote E2E Supabase teardown requires E2E_DESTRUCTIVE_TARGET_CONFIRM=dedicated-e2e-supabase',
    );
  }
}

function assertAllowedDatabaseUrl(name, value) {
  if (!value) {
    return;
  }

  const url = new URL(value);
  const isLocalHost = ['db', 'localhost', '127.0.0.1'].includes(url.hostname);
  const database = url.pathname.replace(/^\//, '');
  const isE2EDatabase = ['xyz_lms', 'xyz_lms_test'].includes(database);

  if (!isLocalHost || !isE2EDatabase) {
    throw new Error(`${name} must point to the local/E2E database`);
  }
}

function assertSafeTarget(env) {
  requireEnv(env, [
    'NEXT_PUBLIC_SUPABASE_URL',
    'SUPABASE_SERVICE_ROLE_KEY',
    'E2E_SUPABASE_ALLOWED_URL',
    'SUPABASE_STORAGE_BUCKET',
  ]);
  assertAllowedSupabaseUrl(env);
  assertAllowedDatabaseUrl('DATABASE_URL', env.DATABASE_URL);
  assertAllowedDatabaseUrl('TEST_DATABASE_URL', env.TEST_DATABASE_URL);
}

function assertUuidList(field, values) {
  for (const value of values) {
    if (!UUID_PATTERN.test(value)) {
      throw new Error(`Invalid UUID in ${field}: ${value}`);
    }
  }
}

function assertManifestIds(manifest) {
  for (const field of MANIFEST_FIELDS) {
    if (field === 'storageKeys') {
      continue;
    }
    assertUuidList(field, manifest[field] ?? []);
  }
}

function assertExactStorageKey(key) {
  if (
    !key ||
    key.includes('*') ||
    key.endsWith('/') ||
    key === 'modules' ||
    key.includes('..') ||
    !key.startsWith('modules/')
  ) {
    throw new Error(`Refusing broad or invalid storage cleanup key: ${key}`);
  }

  if (
    !ASSET_STORAGE_KEY_PATTERN.test(key) &&
    !TRANSCRIPT_STORAGE_KEY_PATTERN.test(key) &&
    !LEGACY_DIRECT_TRANSCRIPT_STORAGE_KEY_PATTERN.test(key)
  ) {
    throw new Error(`Refusing non-object storage cleanup key: ${key}`);
  }
}

function sqlLiteral(value) {
  return `'${String(value).replaceAll("'", "''")}'`;
}

function uuidList(values) {
  return values.map((value) => `${sqlLiteral(value)}::uuid`).join(', ');
}

function runPsql(sql) {
  const result = spawnSync(
    'docker',
    [
      'compose',
      'exec',
      '-T',
      APP_DATABASE_SERVICE,
      'psql',
      '-v',
      'ON_ERROR_STOP=1',
      '-U',
      APP_DATABASE_USER,
      '-d',
      APP_DATABASE_NAME,
      '-tA',
    ],
    {
      input: sql,
      encoding: 'utf8',
    },
  );

  if (result.status !== 0) {
    throw new Error(`psql failed:\n${result.stderr || result.stdout}`);
  }

  return result.stdout
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function deleteWhere(table, conditions) {
  const activeConditions = conditions.filter(Boolean);
  if (activeConditions.length === 0) {
    return 0;
  }

  const rows = runPsql(`
WITH deleted AS (
  DELETE FROM ${table}
  WHERE ${activeConditions.map((condition) => `(${condition})`).join(' OR ')}
  RETURNING 1
)
SELECT count(*)::int FROM deleted;
`);

  return Number(rows.at(-1) ?? 0);
}

function selectStorageKeys(manifest) {
  const keys = new Set(manifest.storageKeys ?? []);

  if ((manifest.assetIds ?? []).length > 0) {
    for (const key of runPsql(`
SELECT storage_key
FROM section_assets
WHERE id IN (${uuidList(manifest.assetIds)});
`)) {
      keys.add(key);
    }
  }

  if ((manifest.sectionIds ?? []).length > 0) {
    for (const key of runPsql(`
SELECT storage_key
FROM section_assets
WHERE module_section_id IN (${uuidList(manifest.sectionIds)});
`)) {
      keys.add(key);
    }
  }

  if ((manifest.transcriptIds ?? []).length > 0) {
    for (const key of runPsql(`
SELECT storage_key
FROM transcripts
WHERE id IN (${uuidList(manifest.transcriptIds)});
`)) {
      keys.add(key);
    }
  }

  if ((manifest.sectionIds ?? []).length > 0) {
    for (const key of runPsql(`
SELECT storage_key
FROM transcripts
WHERE module_section_id IN (${uuidList(manifest.sectionIds)});
`)) {
      keys.add(key);
    }
  }

  return [...keys].filter(Boolean);
}

function adminHeaders(env) {
  return {
    apikey: env.SUPABASE_SERVICE_ROLE_KEY,
    authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`,
    'content-type': 'application/json',
  };
}

async function supabaseAdminFetch(env, path, init = {}) {
  const response = await fetch(`${env.NEXT_PUBLIC_SUPABASE_URL}${path}`, {
    ...init,
    headers: {
      ...adminHeaders(env),
      ...(init.headers ?? {}),
    },
  });
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const message = body?.msg ?? body?.message ?? body?.error ?? response.statusText;
    throw new Error(`Supabase Admin API ${init.method ?? 'GET'} ${path} failed: ${message}`);
  }

  return body;
}

async function deleteStorageKeys(env, storageKeys) {
  let deleted = 0;

  for (const key of storageKeys) {
    assertExactStorageKey(key);
    await supabaseAdminFetch(
      env,
      `/storage/v1/object/${encodeURIComponent(env.SUPABASE_STORAGE_BUCKET)}`,
      {
        method: 'DELETE',
        body: JSON.stringify({ prefixes: [key] }),
      },
    );
    deleted += 1;
  }

  return deleted;
}

async function deleteAuthUsers(env, authUserIds) {
  if (authUserIds.length === 0) {
    return 0;
  }

  const body = await supabaseAdminFetch(env, '/auth/v1/admin/users?per_page=1000&page=1');
  const users = Array.isArray(body?.users) ? body.users : [];
  let deleted = 0;

  for (const authUserId of authUserIds) {
    const user = users.find((candidate) => candidate.id === authUserId);
    if (!user) {
      continue;
    }
    if (!String(user.email ?? '').endsWith(`@${E2E_ACTOR_DOMAIN}`)) {
      throw new Error(`Refusing auth cleanup for non-E2E email: ${user.email}`);
    }
    await supabaseAdminFetch(env, `/auth/v1/admin/users/${authUserId}`, {
      method: 'DELETE',
    });
    deleted += 1;
  }

  return deleted;
}

function validateManifestForTeardown(identifier) {
  const env = loadEnv();
  assertSafeTarget(env);

  const { manifest, path } = loadManifest(identifier);
  assertManifestIds(manifest);
  for (const key of manifest.storageKeys ?? []) {
    assertExactStorageKey(key);
  }

  return { env, manifest, path };
}

async function teardown(identifier) {
  const { env, manifest, path } = validateManifestForTeardown(identifier);

  const definitionScope =
    manifest.moduleIds.length > 0
      ? `quiz_definition_id IN (SELECT id FROM quiz_definitions WHERE module_id IN (${uuidList(manifest.moduleIds)}))`
      : '';
  const studentScope =
    manifest.appUserIds.length > 0 ? `student_id IN (${uuidList(manifest.appUserIds)})` : '';
  const attemptScope = [definitionScope, studentScope].filter(Boolean).join(' OR ');
  const questionScope = attemptScope
    ? `quiz_attempt_id IN (SELECT id FROM quiz_attempts WHERE ${attemptScope})`
    : '';
  const poolScope =
    manifest.sectionIds.length > 0
      ? `section_question_pool_id IN (SELECT id FROM section_question_pools WHERE module_section_id IN (${uuidList(manifest.sectionIds)}))`
      : '';

  const storageKeys = selectStorageKeys(manifest);
  const summary = {
    manifest: path,
    runId: manifest.runId,
    storageObjects: await deleteStorageKeys(env, storageKeys),
    studentAnswers: deleteWhere('student_answers', [
      questionScope
        ? `quiz_question_id IN (SELECT id FROM quiz_questions WHERE ${questionScope})`
        : '',
    ]),
    answerOptions: deleteWhere('answer_options', [
      questionScope
        ? `quiz_question_id IN (SELECT id FROM quiz_questions WHERE ${questionScope})`
        : '',
    ]),
    quizQuestions: deleteWhere('quiz_questions', [questionScope]),
    mistakeRecords: deleteWhere('mistake_records', [
      manifest.moduleIds.length > 0 ? `module_id IN (${uuidList(manifest.moduleIds)})` : '',
      manifest.appUserIds.length > 0 ? `student_id IN (${uuidList(manifest.appUserIds)})` : '',
    ]),
    quizAttempts: deleteWhere('quiz_attempts', [attemptScope]),
    poolQuestions: deleteWhere('pool_questions', [poolScope]),
    sectionQuestionPools: deleteWhere('section_question_pools', [
      manifest.sectionIds.length > 0 ? `module_section_id IN (${uuidList(manifest.sectionIds)})` : '',
    ]),
    quizDefinitions: deleteWhere('quiz_definitions', [
      manifest.moduleIds.length > 0 ? `module_id IN (${uuidList(manifest.moduleIds)})` : '',
    ]),
    assessmentScopes: deleteWhere('assessment_scopes', [
      manifest.moduleIds.length > 0 ? `module_id IN (${uuidList(manifest.moduleIds)})` : '',
    ]),
    // Stage 4.5: generated summaries reference ai_request_logs (RESTRICT). They must be removed
    // BEFORE deleting ingestion_jobs (whose delete cascades ai_request_logs), or the cascade hits
    // the RESTRICT FK. Scoped by the run's transcripts/sections.
    generatedSummaries: deleteWhere('generated_lecture_summaries', [
      manifest.transcriptIds.length > 0
        ? `transcript_id IN (${uuidList(manifest.transcriptIds)})`
        : '',
      manifest.sectionIds.length > 0
        ? `module_section_id IN (${uuidList(manifest.sectionIds)})`
        : '',
    ]),
    transcriptChunks: deleteWhere('transcript_chunks', [
      manifest.transcriptChunkIds.length > 0
        ? `id IN (${uuidList(manifest.transcriptChunkIds)})`
        : '',
      manifest.transcriptIds.length > 0
        ? `transcript_id IN (${uuidList(manifest.transcriptIds)})`
        : '',
      manifest.sectionIds.length > 0
        ? `transcript_id IN (SELECT id FROM transcripts WHERE module_section_id IN (${uuidList(manifest.sectionIds)}))`
        : '',
    ]),
    ingestionJobs: deleteWhere('ingestion_jobs', [
      manifest.ingestionJobIds.length > 0
        ? `id IN (${uuidList(manifest.ingestionJobIds)})`
        : '',
      manifest.transcriptIds.length > 0
        ? `transcript_id IN (${uuidList(manifest.transcriptIds)})`
        : '',
      manifest.sectionIds.length > 0
        ? `transcript_id IN (SELECT id FROM transcripts WHERE module_section_id IN (${uuidList(manifest.sectionIds)}))`
        : '',
    ]),
    aiRequestLogs: deleteWhere('ai_request_logs', [
      manifest.aiRequestLogIds.length > 0 ? `id IN (${uuidList(manifest.aiRequestLogIds)})` : '',
    ]),
    transcriptSegments: deleteWhere('transcript_segments', [
      manifest.transcriptSegmentIds.length > 0
        ? `id IN (${uuidList(manifest.transcriptSegmentIds)})`
        : '',
      manifest.transcriptIds.length > 0
        ? `transcript_id IN (${uuidList(manifest.transcriptIds)})`
        : '',
      manifest.sectionIds.length > 0
        ? `transcript_id IN (SELECT id FROM transcripts WHERE module_section_id IN (${uuidList(manifest.sectionIds)}))`
        : '',
    ]),
    transcripts: deleteWhere('transcripts', [
      manifest.transcriptIds.length > 0 ? `id IN (${uuidList(manifest.transcriptIds)})` : '',
      manifest.sectionIds.length > 0
        ? `module_section_id IN (${uuidList(manifest.sectionIds)})`
        : '',
    ]),
    sectionAssets: deleteWhere('section_assets', [
      manifest.assetIds.length > 0 ? `id IN (${uuidList(manifest.assetIds)})` : '',
      manifest.sectionIds.length > 0
        ? `module_section_id IN (${uuidList(manifest.sectionIds)})`
        : '',
    ]),
    moduleSections: deleteWhere('module_sections', [
      manifest.sectionIds.length > 0 ? `id IN (${uuidList(manifest.sectionIds)})` : '',
      manifest.moduleIds.length > 0
        ? `course_module_id IN (${uuidList(manifest.moduleIds)})`
        : '',
    ]),
    courseMemberships: deleteWhere('course_memberships', [
      manifest.membershipIds.length > 0
        ? `id IN (${uuidList(manifest.membershipIds)})`
        : '',
      manifest.moduleIds.length > 0 ? `module_id IN (${uuidList(manifest.moduleIds)})` : '',
    ]),
    courseModules: deleteWhere('course_modules', [
      manifest.moduleIds.length > 0 ? `id IN (${uuidList(manifest.moduleIds)})` : '',
    ]),
    appUsers: deleteWhere('app_users', [
      manifest.appUserIds.length > 0 ? `id IN (${uuidList(manifest.appUserIds)})` : '',
    ]),
    authUsers: await deleteAuthUsers(env, manifest.authUserIds),
  };

  console.log(JSON.stringify(summary, null, 2));
}

const [commandOrIdentifier, maybeIdentifier] = process.argv.slice(2);
const isValidateOnly = commandOrIdentifier === 'validate';
const identifier = isValidateOnly ? maybeIdentifier : commandOrIdentifier;

const operation = isValidateOnly
  ? Promise.resolve().then(() => {
      const { manifest, path } = validateManifestForTeardown(identifier);
      console.log(
        JSON.stringify(
          {
            manifest: path,
            runId: manifest.runId,
            valid: true,
          },
          null,
          2,
        ),
      );
    })
  : teardown(identifier);

operation.catch((error) => {
  console.error(error.message);
  process.exit(1);
});
