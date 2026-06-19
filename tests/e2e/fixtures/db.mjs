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

// Stage 5.5: assignment/supplementary sections are no longer generated (D12), but the enum still
// exists. Tests that need a non-generated section type (e.g. the transcript unsupported-type guard)
// seed one directly. order_index = max(order_index)+1 for the module so it never collides with the
// uq_module_sections_module_order unique constraint. Returns the new section in SectionRow shape.
export function insertSection(moduleId, { type, title, publishStatus = 'draft' }) {
  assertUuid(moduleId, 'moduleId');
  return runPsqlJson(`
WITH next_index AS (
  SELECT coalesce(max(order_index), 0) + 1 AS oi
  FROM module_sections
  WHERE course_module_id = ${sqlLiteral(moduleId)}::uuid
),
inserted AS (
INSERT INTO module_sections (id, course_module_id, title, type, order_index, publish_status, status)
SELECT gen_random_uuid(), ${sqlLiteral(moduleId)}::uuid, ${sqlLiteral(title)}, ${sqlLiteral(type)},
       next_index.oi, ${sqlLiteral(publishStatus)}, 'active'
FROM next_index
RETURNING id, title, type, order_index, publish_status
)
SELECT json_build_object(
  'id', id, 'title', title, 'type', type, 'orderIndex', order_index, 'publishStatus', publish_status
)::text
FROM inserted;
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

// E2E-only: create an active transcript that is visibly "processing" for assistant readiness
// without racing the real transcript worker. No chunks/embeddings are inserted.
export function seedProcessingTranscriptForSection(sectionId, lecturerEmail) {
  assertUuid(sectionId, 'sectionId');
  const row = runPsqlJson(`
WITH lecturer AS (
  SELECT id FROM app_users WHERE email = ${sqlLiteral(lecturerEmail)} LIMIT 1
),
inserted AS (
  INSERT INTO transcripts (
    id,
    module_section_id,
    source_type,
    original_file_name,
    storage_key,
    mime_type,
    file_size,
    checksum,
    status,
    uploaded_by_user_id,
    lifecycle_state
  )
  SELECT
    gen_random_uuid(),
    ${sqlLiteral(sectionId)}::uuid,
    'manual_upload',
    'processing.vtt',
    'e2e/' || gen_random_uuid()::text || '/processing.vtt',
    'text/vtt',
    10,
    encode(sha256(gen_random_uuid()::text::bytea), 'hex'),
    'chunking',
    lecturer.id,
    'active'
  FROM lecturer
  RETURNING id
)
SELECT json_build_object('id', id)::text FROM inserted;
`);
  if (!row?.id) throw new Error(`Failed to seed processing transcript for ${sectionId}`);
  return row.id;
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

// --- Stage 8.1: assistant conversations + messages ------------------------------------------------
export function getAssistantConversations(studentId, sectionId) {
  assertUuid(studentId, 'studentId');
  assertUuid(sectionId, 'sectionId');
  return runPsqlJson(`
SELECT coalesce(json_agg(json_build_object(
  'id', id,
  'conversationKind', conversation_kind,
  'attachedSectionId', attached_section_id
) ORDER BY created_at), '[]'::json)::text
FROM assistant_conversations
WHERE student_id = ${sqlLiteral(studentId)}::uuid
  AND attached_section_id = ${sqlLiteral(sectionId)}::uuid;
`);
}

export function countAssistantConversations(studentId, sectionId) {
  assertUuid(studentId, 'studentId');
  assertUuid(sectionId, 'sectionId');
  const rows = runPsqlRows(`
SELECT count(*)::int
FROM assistant_conversations
WHERE student_id = ${sqlLiteral(studentId)}::uuid
  AND attached_section_id = ${sqlLiteral(sectionId)}::uuid
  AND conversation_kind = 'lecture_default';
`);
  return Number(rows.at(-1) ?? 0);
}

export function getAssistantMessages(conversationId) {
  assertUuid(conversationId, 'conversationId');
  return runPsqlJson(`
SELECT coalesce(json_agg(json_build_object(
  'id', id,
  'role', role,
  'status', status,
  'content', content,
  'aiRequestLogId', ai_request_log_id,
  'clientIdempotencyKey', client_idempotency_key
) ORDER BY created_at, id), '[]'::json)::text
FROM assistant_messages
WHERE conversation_id = ${sqlLiteral(conversationId)}::uuid;
`);
}

// The AIRequestLog feature values for a conversation's completed assistant turns — proves each answer
// ran through the gateway with feature='assistant' (Stage 8.1 gate).
export function getAssistantRequestLogFeatures(conversationId) {
  assertUuid(conversationId, 'conversationId');
  return runPsqlJson(`
SELECT coalesce(json_agg(arl.feature ORDER BY arl.created_at), '[]'::json)::text
FROM assistant_messages am
JOIN ai_request_logs arl ON arl.id = am.ai_request_log_id
WHERE am.conversation_id = ${sqlLiteral(conversationId)}::uuid;
`);
}

// Stage 8.2 — the text of a transcript's first (lowest-index) embedded chunk. The grounding gate asks
// this verbatim: with the deterministic embedding encoder, identical text → cosine distance 0 (well
// under the relevance threshold) → a lecture_grounded answer. Reads the NORMALIZED chunk text (what
// retrieval actually compares + injects), never the raw transcript segment.
export function getFirstTranscriptChunkText(transcriptId) {
  assertUuid(transcriptId, 'transcriptId');
  // JSON round-trip so the exact text (incl. any internal whitespace) survives psql's line splitting —
  // the gate sends it back verbatim and the deterministic encoder needs a byte-identical query.
  const row = runPsqlJson(`
SELECT json_build_object('text', text)::text
FROM transcript_chunks
WHERE transcript_id = ${sqlLiteral(transcriptId)}::uuid
  AND embedding IS NOT NULL
ORDER BY chunk_index
LIMIT 1;
`);
  if (!row || !row.text) throw new Error(`No embedded chunk found for transcript ${transcriptId}`);
  return row.text;
}

// Stage 8.2 — the backend-derived grounding outcome per assistant turn (decision 3: groundingStatus is
// set server-side, never parsed from prose). Lets the gate assert the DB truth behind the UI label/basis.
export function getAssistantMessageGrounding(conversationId) {
  assertUuid(conversationId, 'conversationId');
  return runPsqlJson(`
SELECT coalesce(json_agg(json_build_object(
  'role', role,
  'status', status,
  'groundingStatus', grounding_status,
  'aiRequestLogId', ai_request_log_id
) ORDER BY created_at, id), '[]'::json)::text
FROM assistant_messages
WHERE conversation_id = ${sqlLiteral(conversationId)}::uuid;
`);
}

// --- Stage 8.4: conversation lifecycle (soft-delete, title source, activity) ----------------------
// Full lifecycle view of one conversation — soft-delete tombstone + title source + activity ordering.
export function getAssistantConversationLifecycle(conversationId) {
  assertUuid(conversationId, 'conversationId');
  return runPsqlJson(`
SELECT json_build_object(
  'id', id,
  'title', title,
  'titleSource', title_source,
  'deletedAt', deleted_at,
  'lastActivityAt', last_activity_at,
  'conversationKind', conversation_kind
)::text
FROM assistant_conversations
WHERE id = ${sqlLiteral(conversationId)}::uuid
LIMIT 1;
`);
}

// Count of ACTIVE (non-soft-deleted) lecture_default conversations for (student, section), so
// delete-then-reopen assertions are precise — the tombstone must NOT count (invariant A).
export function countActiveAssistantConversations(studentId, sectionId) {
  assertUuid(studentId, 'studentId');
  assertUuid(sectionId, 'sectionId');
  const rows = runPsqlRows(`
SELECT count(*)::int
FROM assistant_conversations
WHERE student_id = ${sqlLiteral(studentId)}::uuid
  AND attached_section_id = ${sqlLiteral(sectionId)}::uuid
  AND conversation_kind = 'lecture_default'
  AND deleted_at IS NULL;
`);
  return Number(rows.at(-1) ?? 0);
}

// Deterministically seed a PENDING assistant turn (a completed user message + a pending assistant reply)
// WITHOUT enqueuing a job, so the conversation shows an in-flight answer with no timing race — used by the
// delete-while-pending gate (invariant E). E2E-only. Returns the assistant message id. assistant_messages
// has no server default for id, so each row supplies gen_random_uuid().
export function seedPendingAssistantTurn(conversationId, question = 'Pending question for the delete-while-pending gate') {
  assertUuid(conversationId, 'conversationId');
  const row = runPsqlJson(`
WITH user_msg AS (
  INSERT INTO assistant_messages (id, conversation_id, role, status, content, retryable)
  VALUES (gen_random_uuid(), ${sqlLiteral(conversationId)}::uuid, 'user', 'completed', ${sqlLiteral(question)}, false)
  RETURNING id
),
assistant_msg AS (
  INSERT INTO assistant_messages (id, conversation_id, role, status, prompt_message_id, retryable)
  SELECT gen_random_uuid(), ${sqlLiteral(conversationId)}::uuid, 'assistant', 'pending', user_msg.id, false
  FROM user_msg
  RETURNING id
)
SELECT json_build_object('assistantMessageId', (SELECT id FROM assistant_msg))::text;
`);
  if (!row?.assistantMessageId) throw new Error(`Failed to seed pending turn for ${conversationId}`);
  return row.assistantMessageId;
}

// Stage 4.7 R1 — canary validity: how many of a transcript's SEGMENTS (raw transcript text) contain a
// needle. Proves the G3 sentinel actually rode the transcript that backs the student's summary (not an
// orphan), so its absence from the student surface is a live guarantee, not a vacuous one.
export function countTranscriptSegmentsContaining(transcriptId, needle) {
  assertUuid(transcriptId, 'transcriptId');
  const rows = runPsqlRows(`
SELECT count(*)::int
FROM transcript_segments
WHERE transcript_id = ${sqlLiteral(transcriptId)}::uuid
  AND text LIKE ${sqlLiteral('%' + needle + '%')};
`);
  return Number(rows.at(-1) ?? 0);
}
