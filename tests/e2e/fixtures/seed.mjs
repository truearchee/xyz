#!/usr/bin/env node

import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const ENV_PATH = resolve(process.cwd(), '.env.e2e');
const APP_DATABASE_SERVICE = 'db';
const APP_DATABASE_NAME = 'xyz_lms';
const APP_DATABASE_USER = 'postgres';

const fixtureUsers = [
  {
    key: 'admin',
    id: '10000000-0000-4000-8000-000000000001',
    email: 'admin_e2e@example.test',
    fullName: 'Admin E2E',
    role: 'admin',
  },
  {
    key: 'lecturer',
    id: '10000000-0000-4000-8000-000000000002',
    email: 'lecturer_e2e@example.test',
    fullName: 'Lecturer E2E',
    role: 'lecturer',
  },
  {
    key: 'lecturerUnassigned',
    id: '10000000-0000-4000-8000-000000000003',
    email: 'lecturer_unassigned_e2e@example.test',
    fullName: 'Lecturer Unassigned E2E',
    role: 'lecturer',
  },
  {
    key: 'student',
    id: '10000000-0000-4000-8000-000000000004',
    email: 'student_e2e@example.test',
    fullName: 'Student E2E',
    role: 'student',
  },
];

const fixtureIds = {
  module: '20000000-0000-4000-8000-000000000001',
  lecturerMembership: '30000000-0000-4000-8000-000000000001',
  studentMembership: '30000000-0000-4000-8000-000000000002',
  draftSection: '40000000-0000-4000-8000-000000000001',
  publishedSection: '40000000-0000-4000-8000-000000000002',
};

function loadEnv() {
  if (!existsSync(ENV_PATH)) {
    throw new Error('.env.e2e is required before seeding E2E fixtures');
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

async function listAuthUsers(env) {
  const body = await supabaseAdminFetch(env, '/auth/v1/admin/users?per_page=1000&page=1');
  return Array.isArray(body?.users) ? body.users : [];
}

async function ensureAuthUser(env, user) {
  const users = await listAuthUsers(env);
  const existing = users.find((candidate) => candidate.email === user.email);
  const payload = {
    email: user.email,
    password: env.E2E_TEST_PASSWORD,
    email_confirm: true,
    user_metadata: {
      full_name: user.fullName,
      e2e_fixture: '4.3.5a',
    },
  };

  if (existing?.id) {
    const updated = await supabaseAdminFetch(env, `/auth/v1/admin/users/${existing.id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
    return updated?.user ?? updated;
  }

  const created = await supabaseAdminFetch(env, '/auth/v1/admin/users', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return created?.user ?? created;
}

function sqlLiteral(value) {
  return `'${String(value).replaceAll("'", "''")}'`;
}

function appUserValues(authUsersByEmail) {
  return fixtureUsers
    .map((user) => {
      const authUser = authUsersByEmail.get(user.email);
      if (!authUser?.id) {
        throw new Error(`Auth user was not created for ${user.email}`);
      }
      return `(${sqlLiteral(user.id)}::uuid, ${sqlLiteral(authUser.id)}, ${sqlLiteral(
        user.email,
      )}, ${sqlLiteral(user.fullName)}, ${sqlLiteral(user.role)}, true, 'UTC')`;
    })
    .join(',\n    ');
}

function seedSql(authUsersByEmail) {
  const adminEmails = fixtureUsers.map((user) => sqlLiteral(user.email)).join(', ');
  const lecturer = fixtureUsers.find((user) => user.key === 'lecturer');
  const student = fixtureUsers.find((user) => user.key === 'student');
  return `
BEGIN;

INSERT INTO app_users (id, auth_provider_id, email, full_name, role, is_active, timezone)
VALUES
    ${appUserValues(authUsersByEmail)}
ON CONFLICT (email) DO UPDATE SET
    auth_provider_id = EXCLUDED.auth_provider_id,
    full_name = EXCLUDED.full_name,
    role = EXCLUDED.role,
    is_active = true,
    timezone = EXCLUDED.timezone,
    updated_at = now();

INSERT INTO course_modules (
    id,
    title,
    description,
    owner_id,
    timezone,
    starts_on,
    ends_on,
    is_active
)
SELECT
    ${sqlLiteral(fixtureIds.module)}::uuid,
    'e2e_module',
    'Deterministic module for 4.3.5a browser edge tests',
    id,
    'UTC',
    DATE '2026-01-12',
    DATE '2026-05-01',
    true
FROM app_users
WHERE email = ${sqlLiteral(lecturer.email)}
ON CONFLICT (id) DO UPDATE SET
    title = EXCLUDED.title,
    description = EXCLUDED.description,
    owner_id = EXCLUDED.owner_id,
    timezone = EXCLUDED.timezone,
    starts_on = EXCLUDED.starts_on,
    ends_on = EXCLUDED.ends_on,
    is_active = true,
    updated_at = now();

DELETE FROM course_memberships
WHERE module_id = ${sqlLiteral(fixtureIds.module)}::uuid
  AND user_id IN (SELECT id FROM app_users WHERE email IN (${adminEmails}));

INSERT INTO course_memberships (id, user_id, module_id, role, status, archived_at)
SELECT
    ${sqlLiteral(fixtureIds.lecturerMembership)}::uuid,
    id,
    ${sqlLiteral(fixtureIds.module)}::uuid,
    'lecturer',
    'active',
    NULL
FROM app_users
WHERE email = ${sqlLiteral(lecturer.email)}
ON CONFLICT (id) DO UPDATE SET
    user_id = EXCLUDED.user_id,
    module_id = EXCLUDED.module_id,
    role = EXCLUDED.role,
    status = 'active',
    archived_at = NULL,
    updated_at = now();

INSERT INTO course_memberships (id, user_id, module_id, role, status, archived_at)
SELECT
    ${sqlLiteral(fixtureIds.studentMembership)}::uuid,
    id,
    ${sqlLiteral(fixtureIds.module)}::uuid,
    'student',
    'active',
    NULL
FROM app_users
WHERE email = ${sqlLiteral(student.email)}
ON CONFLICT (id) DO UPDATE SET
    user_id = EXCLUDED.user_id,
    module_id = EXCLUDED.module_id,
    role = EXCLUDED.role,
    status = 'active',
    archived_at = NULL,
    updated_at = now();

INSERT INTO module_sections (
    id,
    course_module_id,
    title,
    type,
    order_index,
    week_number,
    session_date,
    due_at,
    publish_status,
    lecturer_notes,
    status,
    archived_at
)
VALUES
    (
      ${sqlLiteral(fixtureIds.draftSection)}::uuid,
      ${sqlLiteral(fixtureIds.module)}::uuid,
      'lecture_section',
      'lecture',
      1,
      1,
      DATE '2026-01-12',
      NULL,
      'draft',
      NULL,
      'active',
      NULL
    ),
    (
      ${sqlLiteral(fixtureIds.publishedSection)}::uuid,
      ${sqlLiteral(fixtureIds.module)}::uuid,
      'published_section',
      'lecture',
      2,
      1,
      DATE '2026-01-13',
      NULL,
      'published',
      NULL,
      'active',
      NULL
    )
ON CONFLICT (id) DO UPDATE SET
    course_module_id = EXCLUDED.course_module_id,
    title = EXCLUDED.title,
    type = EXCLUDED.type,
    order_index = EXCLUDED.order_index,
    week_number = EXCLUDED.week_number,
    session_date = EXCLUDED.session_date,
    due_at = EXCLUDED.due_at,
    publish_status = EXCLUDED.publish_status,
    lecturer_notes = EXCLUDED.lecturer_notes,
    status = 'active',
    archived_at = NULL,
    updated_at = now();

COMMIT;

SELECT json_build_object(
    'appUsers', (SELECT count(*) FROM app_users WHERE email IN (${adminEmails})),
    'modules', (SELECT count(*) FROM course_modules WHERE id = ${sqlLiteral(fixtureIds.module)}::uuid),
    'activeMemberships', (
      SELECT count(*)
      FROM course_memberships
      WHERE module_id = ${sqlLiteral(fixtureIds.module)}::uuid AND status = 'active'
    ),
    'sections', (
      SELECT count(*)
      FROM module_sections
      WHERE id IN (
        ${sqlLiteral(fixtureIds.draftSection)}::uuid,
        ${sqlLiteral(fixtureIds.publishedSection)}::uuid
      )
    ),
    'draftSections', (
      SELECT count(*)
      FROM module_sections
      WHERE id = ${sqlLiteral(fixtureIds.draftSection)}::uuid AND publish_status = 'draft'
    ),
    'publishedSections', (
      SELECT count(*)
      FROM module_sections
      WHERE id = ${sqlLiteral(fixtureIds.publishedSection)}::uuid AND publish_status = 'published'
    )
)::text;
`;
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
    .filter(Boolean)
    .at(-1);
}

function cleanupStorageKeyDryRun(key) {
  if (!key || key.includes('*') || key.endsWith('/') || key === 'modules') {
    throw new Error('Storage cleanup requires an exact object key, not a broad path');
  }
  console.log(`Storage cleanup dry run: would delete exact key only: ${key}`);
}

async function main() {
  const env = loadEnv();
  requireEnv(env, [
    'NEXT_PUBLIC_SUPABASE_URL',
    'NEXT_PUBLIC_SUPABASE_ANON_KEY',
    'SUPABASE_SERVICE_ROLE_KEY',
    'NEXT_PUBLIC_API_BASE_URL',
    'E2E_SUPABASE_ALLOWED_URL',
    'E2E_TEST_PASSWORD',
    'SUPABASE_URL',
    'SUPABASE_SECRET_KEY',
    'SUPABASE_JWKS_URL',
    'SUPABASE_JWT_AUDIENCE',
    'SUPABASE_JWT_ISSUER',
    'SUPABASE_STORAGE_BUCKET',
  ]);
  assertAllowedSupabaseUrl(env);

  const [command, maybeKey] = process.argv.slice(2);
  if (command === 'cleanup-storage-dry-run') {
    cleanupStorageKeyDryRun(maybeKey);
    return;
  }
  if (command && command !== 'seed') {
    throw new Error(`Unknown command: ${command}`);
  }

  const authUsers = await Promise.all(
    fixtureUsers.map((user) => ensureAuthUser(env, user)),
  );
  const authUsersByEmail = new Map(authUsers.map((user) => [user.email, user]));
  const summary = runPsql(seedSql(authUsersByEmail));

  console.log('Seeded Supabase Auth users:', authUsers.length);
  console.log('Seeded app DB fixture summary:', summary);
  console.log('Storage cleanup: no broad path deletion performed by seed.');
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
