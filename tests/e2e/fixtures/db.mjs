import { execFileSync } from 'node:child_process';

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function assertUuid(value, label = 'uuid') {
  if (!UUID_PATTERN.test(String(value))) {
    throw new Error(`Invalid ${label}: ${value}`);
  }
}

export function sqlLiteral(value) {
  return `'${String(value).replaceAll("'", "''")}'`;
}

export function runPsqlRows(sql) {
  const result = execFileSync(
    'docker',
    [
      'compose',
      'exec',
      '-T',
      'db',
      'psql',
      '-v',
      'ON_ERROR_STOP=1',
      '-U',
      'postgres',
      '-d',
      'xyz_lms',
      '-tA',
    ],
    { encoding: 'utf8', input: sql },
  );

  return result
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

export function runPsqlJson(sql) {
  const rows = runPsqlRows(sql);
  const value = rows.at(-1);
  return value ? JSON.parse(value) : null;
}

export function getAppUserByEmail(email) {
  return runPsqlJson(`
SELECT json_build_object('id', id, 'email', email, 'role', role)::text
FROM app_users
WHERE email = ${sqlLiteral(email)}
LIMIT 1;
`);
}

export function getSectionsForModule(moduleId) {
  assertUuid(moduleId, 'moduleId');
  return runPsqlJson(`
SELECT coalesce(json_agg(
  json_build_object(
    'id', id,
    'title', title,
    'type', type,
    'orderIndex', order_index,
    'publishStatus', publish_status
  )
  ORDER BY order_index
), '[]'::json)::text
FROM module_sections
WHERE course_module_id = ${sqlLiteral(moduleId)}::uuid;
`);
}

export function getMembershipsForModule(moduleId) {
  assertUuid(moduleId, 'moduleId');
  return runPsqlJson(`
SELECT coalesce(json_agg(
  json_build_object('id', id, 'userId', user_id, 'role', role, 'status', status)
  ORDER BY created_at
), '[]'::json)::text
FROM course_memberships
WHERE module_id = ${sqlLiteral(moduleId)}::uuid;
`);
}

export function getActiveTranscriptForSection(sectionId) {
  assertUuid(sectionId, 'sectionId');
  return runPsqlJson(`
SELECT json_build_object(
  'id', id,
  'moduleSectionId', module_section_id,
  'status', status,
  'lifecycleState', lifecycle_state,
  'storageKey', storage_key,
  'originalFileName', original_file_name
)::text
FROM transcripts
WHERE module_section_id = ${sqlLiteral(sectionId)}::uuid
  AND lifecycle_state = 'active'
LIMIT 1;
`);
}

export function getActiveTranscriptCountForSection(sectionId) {
  assertUuid(sectionId, 'sectionId');
  const rows = runPsqlRows(`
SELECT count(*)::int
FROM transcripts
WHERE module_section_id = ${sqlLiteral(sectionId)}::uuid
  AND lifecycle_state = 'active';
`);
  return Number(rows.at(-1) ?? 0);
}

// Stage 4.6: full lifecycle/lineage view of every transcript in a section (active + pending +
// superseded), for replacement-continuity + supersession assertions.
export function getTranscriptsBySection(sectionId) {
  assertUuid(sectionId, 'sectionId');
  return runPsqlJson(`
SELECT coalesce(json_agg(row ORDER BY created_at), '[]'::json)::text
FROM (
  SELECT json_build_object(
    'id', id,
    'lifecycleState', lifecycle_state,
    'status', status,
    'supersededByTranscriptId', superseded_by_transcript_id,
    'replacementOfTranscriptId', replacement_of_transcript_id,
    'supersessionReason', supersession_reason,
    'supersededAt', superseded_at,
    'createdAt', created_at
  ) AS row, created_at
  FROM transcripts
  WHERE module_section_id = ${sqlLiteral(sectionId)}::uuid
) sub;
`);
}

export function getTranscriptById(transcriptId) {
  assertUuid(transcriptId, 'transcriptId');
  return runPsqlJson(`
SELECT json_build_object(
  'id', id,
  'moduleSectionId', module_section_id,
  'status', status,
  'lifecycleState', lifecycle_state,
  'supersededByTranscriptId', superseded_by_transcript_id,
  'supersessionReason', supersession_reason,
  'storageKey', storage_key,
  'originalFileName', original_file_name
)::text
FROM transcripts
WHERE id = ${sqlLiteral(transcriptId)}::uuid
LIMIT 1;
`);
}

export function getTranscriptCounts(transcriptId) {
  assertUuid(transcriptId, 'transcriptId');
  return runPsqlJson(`
SELECT json_build_object(
  'segmentCount', (SELECT count(*)::int FROM transcript_segments WHERE transcript_id = ${sqlLiteral(transcriptId)}::uuid),
  'chunkCount', (SELECT count(*)::int FROM transcript_chunks WHERE transcript_id = ${sqlLiteral(transcriptId)}::uuid),
  'segmentIds', coalesce((SELECT json_agg(id) FROM transcript_segments WHERE transcript_id = ${sqlLiteral(transcriptId)}::uuid), '[]'::json),
  'chunkIds', coalesce((SELECT json_agg(id) FROM transcript_chunks WHERE transcript_id = ${sqlLiteral(transcriptId)}::uuid), '[]'::json)
)::text;
`);
}

export function getIngestionJobsForTranscript(transcriptId) {
  assertUuid(transcriptId, 'transcriptId');
  return runPsqlJson(`
SELECT coalesce(json_agg(
  json_build_object(
    'id', id,
    'jobType', job_type,
    'status', status,
    'resultMetadata', result_metadata,
    'errorMessage', error_message
  )
  ORDER BY job_type, created_at
), '[]'::json)::text
FROM ingestion_jobs
WHERE transcript_id = ${sqlLiteral(transcriptId)}::uuid;
`);
}

export function getTranscriptEmbeddingVerification(transcriptId) {
  assertUuid(transcriptId, 'transcriptId');
  return runPsqlJson(`
WITH target_chunks AS (
  SELECT *
  FROM transcript_chunks
  WHERE transcript_id = ${sqlLiteral(transcriptId)}::uuid
    AND btrim(text) <> ''
),
embed_jobs AS (
  SELECT *
  FROM ingestion_jobs
  WHERE transcript_id = ${sqlLiteral(transcriptId)}::uuid
    AND job_type = 'embed'
)
SELECT json_build_object(
  'embedJobStatus', (
    SELECT status
    FROM embed_jobs
    ORDER BY created_at DESC
    LIMIT 1
  ),
  'embedJobCount', (SELECT count(*)::int FROM embed_jobs),
  'activeEmbedJobCount', (
    SELECT count(*)::int
    FROM embed_jobs
    WHERE status IN ('queued', 'running')
  ),
  'chunkCount', (SELECT count(*)::int FROM target_chunks),
  'embeddedChunkCount', (
    SELECT count(*)::int
    FROM target_chunks
    WHERE embedding IS NOT NULL
  ),
  'vectorDimensions', coalesce((
    SELECT json_agg(DISTINCT vector_dims(embedding))
    FROM target_chunks
    WHERE embedding IS NOT NULL
  ), '[]'::json),
  'provenanceCompleteCount', (
    SELECT count(*)::int
    FROM target_chunks
    WHERE embedding IS NOT NULL
      AND embedding_model IS NOT NULL
      AND embedding_model_revision IS NOT NULL
      AND embedding_dimension = 384
      AND embedding_normalization = 'l2'
      AND embedding_version IS NOT NULL
      AND embedding_input_hash IS NOT NULL
      AND chunking_version IS NOT NULL
  ),
  'embeddingModels', coalesce((
    SELECT json_agg(DISTINCT embedding_model)
    FROM target_chunks
    WHERE embedding_model IS NOT NULL
  ), '[]'::json),
  'embeddingModelRevisions', coalesce((
    SELECT json_agg(DISTINCT embedding_model_revision)
    FROM target_chunks
    WHERE embedding_model_revision IS NOT NULL
  ), '[]'::json),
  'embeddingDimensions', coalesce((
    SELECT json_agg(DISTINCT embedding_dimension)
    FROM target_chunks
    WHERE embedding_dimension IS NOT NULL
  ), '[]'::json),
  'embeddingNormalizations', coalesce((
    SELECT json_agg(DISTINCT embedding_normalization)
    FROM target_chunks
    WHERE embedding_normalization IS NOT NULL
  ), '[]'::json),
  'embeddingVersions', coalesce((
    SELECT json_agg(DISTINCT embedding_version)
    FROM target_chunks
    WHERE embedding_version IS NOT NULL
  ), '[]'::json),
  'chunkingVersions', coalesce((
    SELECT json_agg(DISTINCT chunking_version)
    FROM target_chunks
    WHERE chunking_version IS NOT NULL
  ), '[]'::json)
)::text;
`);
}

export function getTranscriptArtifacts(transcriptId) {
  const transcript = getTranscriptById(transcriptId);
  const counts = getTranscriptCounts(transcriptId);
  const jobs = getIngestionJobsForTranscript(transcriptId);
  return { transcript, counts, jobs };
}

export async function waitForTranscriptCompleted(transcriptId, timeoutMs = 60_000) {
  assertUuid(transcriptId, 'transcriptId');
  const startedAt = Date.now();

  while (Date.now() - startedAt < timeoutMs) {
    const artifacts = getTranscriptArtifacts(transcriptId);
    const parseJob = artifacts.jobs.find((job) => job.jobType === 'parse');
    const chunkJob = artifacts.jobs.find((job) => job.jobType === 'chunk');

    if (
      artifacts.transcript?.status === 'completed' &&
      parseJob?.status === 'completed' &&
      chunkJob?.status === 'completed' &&
      artifacts.counts.segmentCount > 0 &&
      artifacts.counts.chunkCount > 0
    ) {
      return artifacts;
    }

    if (
      artifacts.transcript?.status === 'failed' ||
      parseJob?.status === 'failed' ||
      chunkJob?.status === 'failed'
    ) {
      throw new Error(`Transcript worker failed: ${JSON.stringify({
        transcriptStatus: artifacts.transcript?.status,
        jobs: artifacts.jobs,
      })}`);
    }

    await new Promise((resolve) => setTimeout(resolve, 1000));
  }

  throw new Error(
    `Timed out waiting for transcript ${transcriptId} to complete: ${JSON.stringify(
      getTranscriptArtifacts(transcriptId),
    )}`,
  );
}

export async function waitForTranscriptEmbedded(transcriptId, timeoutMs = 90_000) {
  assertUuid(transcriptId, 'transcriptId');
  const startedAt = Date.now();

  while (Date.now() - startedAt < timeoutMs) {
    const artifacts = getTranscriptArtifacts(transcriptId);
    const embedJob = artifacts.jobs.find((job) => job.jobType === 'embed');
    const verification = getTranscriptEmbeddingVerification(transcriptId);

    if (
      artifacts.transcript?.status === 'completed' &&
      embedJob?.status === 'completed' &&
      verification.chunkCount > 0 &&
      verification.embeddedChunkCount === verification.chunkCount &&
      verification.provenanceCompleteCount === verification.chunkCount
    ) {
      return { ...artifacts, embedding: verification };
    }

    if (artifacts.transcript?.status === 'failed' || embedJob?.status === 'failed') {
      throw new Error(`Transcript embedding failed: ${JSON.stringify({
        transcriptStatus: artifacts.transcript?.status,
        jobs: artifacts.jobs,
        embedding: verification,
      })}`);
    }

    await new Promise((resolve) => setTimeout(resolve, 1000));
  }

  throw new Error(
    `Timed out waiting for transcript ${transcriptId} embedding: ${JSON.stringify({
      artifacts: getTranscriptArtifacts(transcriptId),
      embedding: getTranscriptEmbeddingVerification(transcriptId),
    })}`,
  );
}

// --- Stage 4.5d: generated lecture summaries -------------------------------------------------
export function getGeneratedSummariesForTranscript(transcriptId) {
  assertUuid(transcriptId, 'transcriptId');
  return runPsqlJson(`
SELECT coalesce(json_agg(json_build_object(
  'summaryType', summary_type,
  'backendUsed', backend_used,
  'modelId', model_id,
  'contentSchemaVersion', content_schema_version,
  'aiRequestLogId', ai_request_log_id
) ORDER BY summary_type), '[]'::json)::text
FROM generated_lecture_summaries
WHERE transcript_id = ${sqlLiteral(transcriptId)};
`);
}

export function getSummaryJobStatuses(transcriptId) {
  assertUuid(transcriptId, 'transcriptId');
  return runPsqlJson(`
SELECT coalesce(json_object_agg(job_type, status), '{}'::json)::text
FROM ingestion_jobs
WHERE transcript_id = ${sqlLiteral(transcriptId)}
  AND job_type IN ('generate_brief_summary', 'generate_detailed_summary');
`);
}

// Poll until both summary jobs reach a terminal state (completed/failed). Returns the job-status map.
export async function waitForSummariesSettled(transcriptId, timeoutMs = 120_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const statuses = getSummaryJobStatuses(transcriptId) ?? {};
    const values = Object.values(statuses);
    const settled =
      values.length >= 2 && values.every((status) => status === 'completed' || status === 'failed');
    if (settled) {
      return statuses;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(
    `Timed out waiting for summaries to settle for transcript ${transcriptId}: ${JSON.stringify(
      getSummaryJobStatuses(transcriptId),
    )}`,
  );
}

// Stage 4.5d Gate 2 — AIRequestLog rows for a transcript (fault-path proof).
export function getAiRequestLogsForTranscript(transcriptId) {
  assertUuid(transcriptId, 'transcriptId');
  return runPsqlJson(`
SELECT coalesce(json_agg(json_build_object(
  'feature', arl.feature,
  'status', arl.status,
  'errorCode', arl.error_code,
  'attemptNumber', arl.attempt_number
) ORDER BY arl.attempt_number), '[]'::json)::text
FROM ai_request_logs arl
JOIN ingestion_jobs ij ON ij.id = arl.ingestion_job_id
WHERE ij.transcript_id = ${sqlLiteral(transcriptId)};
`);
}

// Poll until the brief summary job reaches the given terminal failure_category (Gate 2).
export async function waitForSummaryFailure(transcriptId, category, timeoutMs = 90_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const row = runPsqlJson(`
SELECT coalesce(json_agg(json_build_object('jobType', job_type, 'status', status, 'failureCategory', failure_category)), '[]'::json)::text
FROM ingestion_jobs
WHERE transcript_id = ${sqlLiteral(transcriptId)} AND job_type IN ('generate_brief_summary','generate_detailed_summary');
`) ?? [];
    const failed = row.find((j) => j.status === 'failed' && j.failureCategory === category);
    if (failed) {
      return row;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`Timed out waiting for summary failure_category=${category} on ${transcriptId}`);
}

// Stage 4.7 G2 — deterministic SEED of the brief-first state (§14): from a fully-summarized transcript,
// remove the detailed summary artifact and re-open its job to 'running'. The student surface then shows
// brief READY + detailed GENERATING with no timing race. E2E-only.
export function seedDetailedSummaryGenerating(transcriptId) {
  assertUuid(transcriptId, 'transcriptId');
  runPsqlRows(`
DELETE FROM generated_lecture_summaries
WHERE transcript_id = ${sqlLiteral(transcriptId)} AND summary_type = 'detailed_study';
UPDATE ingestion_jobs
SET status = 'running', completed_at = NULL
WHERE transcript_id = ${sqlLiteral(transcriptId)} AND job_type = 'generate_detailed_summary';
`);
}
