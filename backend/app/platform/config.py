import os
from pathlib import Path


class SettingsError(RuntimeError):
    pass


class Settings:
    @property
    def CORS_ORIGINS(self) -> list[str]:
        return self.parse_cors_origins(os.environ.get("CORS_ORIGINS"))

    @staticmethod
    def parse_cors_origins(value: str | list[str] | None) -> list[str]:
        if value is None or value == "":
            return ["http://localhost:3000"]
        if isinstance(value, str):
            return [
                origin.strip().rstrip("/")
                for origin in value.split(",")
                if origin.strip()
            ]
        return value

    @property
    def SUPABASE_URL(self) -> str:
        return self._required("SUPABASE_URL")

    @property
    def SUPABASE_PUBLIC_URL(self) -> str:
        return os.environ.get("SUPABASE_PUBLIC_URL") or self.SUPABASE_URL

    @property
    def SUPABASE_SECRET_KEY(self) -> str:
        return self._required("SUPABASE_SECRET_KEY")

    @property
    def SUPABASE_STORAGE_BUCKET(self) -> str:
        return self._required("SUPABASE_STORAGE_BUCKET")

    @property
    def SUPABASE_STORAGE_URL(self) -> str | None:
        return os.environ.get("SUPABASE_STORAGE_URL")

    @property
    def MAX_SECTION_ASSET_UPLOAD_BYTES(self) -> int:
        raw_value = os.environ.get("MAX_SECTION_ASSET_UPLOAD_BYTES", "26214400")
        try:
            value = int(raw_value)
        except ValueError as exc:
            raise SettingsError(
                "MAX_SECTION_ASSET_UPLOAD_BYTES must be an integer"
            ) from exc
        if value <= 0:
            raise SettingsError("MAX_SECTION_ASSET_UPLOAD_BYTES must be greater than zero")
        return value

    @property
    def MAX_TRANSCRIPT_UPLOAD_BYTES(self) -> int:
        raw_value = os.environ.get("MAX_TRANSCRIPT_UPLOAD_BYTES", "10485760")
        try:
            value = int(raw_value)
        except ValueError as exc:
            raise SettingsError("MAX_TRANSCRIPT_UPLOAD_BYTES must be an integer") from exc
        if value <= 0:
            raise SettingsError("MAX_TRANSCRIPT_UPLOAD_BYTES must be greater than zero")
        return value

    @property
    def SIGNED_READ_URL_TTL_SECONDS(self) -> int:
        raw_value = os.environ.get("SIGNED_READ_URL_TTL_SECONDS", "300")
        try:
            value = int(raw_value)
        except ValueError as exc:
            raise SettingsError("SIGNED_READ_URL_TTL_SECONDS must be an integer") from exc
        if value <= 0:
            raise SettingsError("SIGNED_READ_URL_TTL_SECONDS must be greater than zero")
        return value

    @property
    def EMBEDDING_MODEL_PATH(self) -> Path:
        return Path(
            os.environ.get(
                "EMBEDDING_MODEL_PATH",
                "/opt/models/sentence-transformers/all-MiniLM-L6-v2",
            )
        )

    @property
    def EMBEDDING_MODEL_REVISION(self) -> str:
        return os.environ.get(
            "EMBEDDING_MODEL_REVISION",
            "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
        )

    @property
    def EMBEDDING_BATCH_SIZE(self) -> int:
        raw_value = os.environ.get("EMBEDDING_BATCH_SIZE", "16")
        try:
            value = int(raw_value)
        except ValueError as exc:
            raise SettingsError("EMBEDDING_BATCH_SIZE must be an integer") from exc
        if value <= 0:
            raise SettingsError("EMBEDDING_BATCH_SIZE must be greater than zero")
        return value

    @property
    def EMBEDDING_WORKER_CONCURRENCY(self) -> int:
        raw_value = os.environ.get("EMBEDDING_WORKER_CONCURRENCY", "1")
        try:
            value = int(raw_value)
        except ValueError as exc:
            raise SettingsError("EMBEDDING_WORKER_CONCURRENCY must be an integer") from exc
        if value <= 0:
            raise SettingsError("EMBEDDING_WORKER_CONCURRENCY must be greater than zero")
        return value

    @property
    def EMBEDDING_DEVICE(self) -> str:
        value = os.environ.get("EMBEDDING_DEVICE", "cpu").strip()
        if value != "cpu":
            raise SettingsError("EMBEDDING_DEVICE must be cpu")
        return value

    @property
    def SUPABASE_JWKS_URL(self) -> str:
        return self._required("SUPABASE_JWKS_URL")

    @property
    def SUPABASE_JWT_AUDIENCE(self) -> str:
        return os.environ.get("SUPABASE_JWT_AUDIENCE", "authenticated")

    @property
    def SUPABASE_JWT_ISSUER(self) -> str:
        return self._required("SUPABASE_JWT_ISSUER")

    # ─── Runtime environment ────────────────────────────────────────────────
    @property
    def ENVIRONMENT(self) -> str:
        return os.environ.get("ENVIRONMENT", "development").strip() or "development"

    @property
    def IS_NON_PROD(self) -> bool:
        """Fault injection and debug text are permitted only outside prod/staging."""
        return self.ENVIRONMENT not in {"production", "staging"}

    @property
    def IS_PRODUCTION(self) -> bool:
        """True only in real production. DISTINCT from ``not IS_NON_PROD``: staging is NOT production.
        The known-credential seed-identity bootstrap (4.8b) is gated on this — it must run in STAGING
        (where the smoke needs the seeded lecturer/student) but never auto-create them in production."""
        return self.ENVIRONMENT == "production"

    @property
    def BOOTSTRAP_SEED_IDENTITIES(self) -> bool:
        """Gate the known-credential LECTURER/STUDENT seed identities (4.8b). Requires this flag AND
        ``not IS_PRODUCTION``. The real first ADMIN is gated only by its own BOOTSTRAP_ADMIN_* vars."""
        return self._bool("BOOTSTRAP_SEED_IDENTITIES", default=False)

    @property
    def PIPELINE_FAULT_INJECTION_ENABLED(self) -> bool:
        """Master gate for the Stage 4.6 pipeline fault-injection harness (deterministic forced step
        failure + seeded failed-job records). Default OFF; absent/no-op when off. Distinct from the
        LLM-transport ``LLM_FAULT_INJECTION`` (summary jobs only) — this covers ALL five steps."""
        return self._bool("PIPELINE_FAULT_INJECTION_ENABLED", default=False)

    @property
    def PIPELINE_FAULT_INJECTION(self) -> str | None:
        """Which pipeline step to force-fail when the harness is enabled (one of parse/chunk/embed/
        summary_brief/summary_detailed). Mirrors the ``LLM_FAULT_INJECTION`` value pattern."""
        value = os.environ.get("PIPELINE_FAULT_INJECTION")
        return value.strip() if value and value.strip() else None

    # ─── recovery (Stage 4.6c: stuck-row reaper + storage reconciliation) ────
    @property
    def REAPER_RUN_AT_STARTUP(self) -> bool:
        """Run the stuck-row reaper once at worker startup (singleton-locked; only one worker executes)."""
        return self._bool("REAPER_RUN_AT_STARTUP", default=True)

    @property
    def RECONCILE_AT_STARTUP(self) -> bool:
        """Also run storage reconciliation at worker startup (default off — it lists the bucket; admin-triggered)."""
        return self._bool("RECONCILE_AT_STARTUP", default=False)

    @property
    def REAPER_THRESHOLD_PARSE_SECONDS(self) -> int:
        return self._int("REAPER_THRESHOLD_PARSE_SECONDS", "300", minimum=1)

    @property
    def REAPER_THRESHOLD_CHUNK_SECONDS(self) -> int:
        return self._int("REAPER_THRESHOLD_CHUNK_SECONDS", "300", minimum=1)

    @property
    def REAPER_THRESHOLD_EMBED_SECONDS(self) -> int:
        """Embed scales with transcript size — generous default above any realistic embed run."""
        return self._int("REAPER_THRESHOLD_EMBED_SECONDS", "1800", minimum=1)

    @property
    def REAPER_THRESHOLD_SUMMARY_SECONDS(self) -> int:
        """Summary = prompt timeout + limiter/backoff buffer (> LLM_DETAILED_TIMEOUT_SECONDS)."""
        return self._int("REAPER_THRESHOLD_SUMMARY_SECONDS", "900", minimum=1)

    @property
    def REAPER_ACTION_CAP_PER_RUN(self) -> int:
        """Max rows the reaper acts on per run (safety bound)."""
        return self._int("REAPER_ACTION_CAP_PER_RUN", "100", minimum=1)

    @property
    def RECONCILIATION_MANAGED_PREFIX(self) -> str:
        """Storage prefix the reconciliation job scopes to (transcript keys live under modules/)."""
        return os.environ.get("RECONCILIATION_MANAGED_PREFIX", "modules/")

    @property
    def RECONCILIATION_GRACE_WINDOW_SECONDS(self) -> int:
        """An object is an orphan candidate only if older than this (an in-flight upload looks identical)."""
        return self._int("RECONCILIATION_GRACE_WINDOW_SECONDS", "86400", minimum=0)

    @property
    def RECONCILIATION_DELETION_CAP_PER_RUN(self) -> int:
        return self._int("RECONCILIATION_DELETION_CAP_PER_RUN", "50", minimum=1)

    @property
    def RECONCILIATION_MAX_OBJECTS(self) -> int:
        """Cap on objects scanned per reconciliation run (a hit cap skips missing-ref detection)."""
        return self._int("RECONCILIATION_MAX_OBJECTS", "10000", minimum=1)

    @property
    def RECONCILIATION_CLEANUP_ENABLED(self) -> bool:
        """Cleanup (actual deletion) requires BOTH this flag AND mode='cleanup' on the run. Default off."""
        return self._bool("RECONCILIATION_CLEANUP_ENABLED", default=False)

    @property
    def REDIS_URL(self) -> str:
        return os.environ.get("REDIS_URL", "redis://redis:6379/0")

    @property
    def ENABLE_INTERNAL_SSE_PROBE(self) -> bool:
        """Stage 4.8c (C1, adr-043): register the admin-only ``/internal/sse-probe`` ONLY when set.
        Default off → the route does not exist (404). Allowed ON in staging (gated + admin-auth; the
        4.8d smoke uses it); a future prod build leaves it off."""
        return self._bool("ENABLE_INTERNAL_SSE_PROBE", default=False)

    # ─── Database (Stage 4.8: dual URL — app via pooler, Alembic + advisory lock via direct) ─────
    @property
    def DATABASE_URL(self) -> str | None:
        return os.environ.get("DATABASE_URL")

    @property
    def DIRECT_DATABASE_URL(self) -> str | None:
        """Direct/session endpoint for Alembic + the maintenance advisory lock. Falls back to
        DATABASE_URL locally (single URL); the Supabase session endpoint in staging (adr-041)."""
        return os.environ.get("DIRECT_DATABASE_URL") or self.DATABASE_URL

    @property
    def DATABASE_POOLER(self) -> bool:
        """True when DATABASE_URL is a transaction pooler (prepared statements off, unique stmt
        names). EXPLICIT flag — never inferred from the URL/port, since Supabase's direct and
        transaction-pooler endpoints can both listen on :5432 (a port sniff is a latent bug)."""
        return self._bool("DATABASE_POOLER", default=False)

    # ─── LLM provider + capacity (Stage 4.5) ────────────────────────────────
    @property
    def LLM_PROVIDER(self) -> str:
        """`deterministic` (default; CI/local) or `k2think` (real transport, Stage 4.5b)."""
        value = os.environ.get("LLM_PROVIDER", "deterministic").strip()
        if value not in {"deterministic", "k2think"}:
            raise SettingsError("LLM_PROVIDER must be 'deterministic' or 'k2think'")
        return value

    @property
    def LLM_PROVIDER_BASE_URL(self) -> str:
        return os.environ.get("LLM_PROVIDER_BASE_URL", "https://api.k2think.ai").rstrip("/")

    @property
    def LLM_API_KEY(self) -> str | None:
        """Optional in 4.5a (deterministic). Required only when LLM_PROVIDER='k2think' (4.5b).

        Provider-agnostic ``LLM_*`` namespace is the standard (spec §11): a provider-specific name
        like ``IFM_API_KEY`` would leak the vendor into config and contradict the swappable provider
        boundary.
        """
        return os.environ.get("LLM_API_KEY") or None

    @property
    def ENABLE_DETAILED_SUMMARY(self) -> bool:
        """Stage 4.5c activates detailed generation (default true): the after-embed hook enqueues
        BOTH summary jobs and a transcript can reach overallState='summarized'. 4.5b gated it OFF
        while Think-v0 was the (inaccessible) target; 4.5c runs detailed on the verified K2-Think-v2
        via the Nvidia route (Option A, ADR-025). Set false to suppress detailed (e.g. cost control)."""
        return self._bool("ENABLE_DETAILED_SUMMARY", default=True)

    @property
    def LLM_PROVIDER_JSON_MODE(self) -> bool:
        """Ask the provider for ``response_format={"type":"json_object"}`` (§7.1). Default ON as of the
        4.5.1c real-provider smoke, which CONFIRMED K2-Think-v2 honors it on BOTH routes (nvidia map/reduce
        + cerebras brief: HTTP200, finish_reason=stop, clean JSON). Decisive for the map phase: WITHOUT it
        the reasoning model spent the whole token budget thinking ("We need to produce…") and hit
        finish_reason=length before emitting JSON → not_json on ~33% of map calls; WITH it the model emits
        the JSON object directly. The tolerant-extract validator + the map/reduce in-call retry remain the
        safety net. (The deterministic test provider ignores this — CI/tests are unaffected.)"""
        return self._bool("LLM_PROVIDER_JSON_MODE", default=True)

    @property
    def LLM_PROVIDER_TIMEOUT_SECONDS(self) -> int:
        """HTTP transport timeout for the BRIEF/base call; a timeout maps to provider_transient (§8)."""
        return self._int("LLM_PROVIDER_TIMEOUT_SECONDS", "60", minimum=1)

    @property
    def LLM_DETAILED_TIMEOUT_SECONDS(self) -> int:
        """HTTP transport timeout for the DETAILED (Nvidia route) call. K2-Think-v2 reasons inline then
        emits the full structured DetailedSummary, which needs materially more wall-clock than brief —
        60s timed it out repeatably (F-4.5-49). The provider selects this per-route (detailed > brief).
        Kept >= the lease TTL so a legitimate long call is not reclaimed mid-flight."""
        return self._int("LLM_DETAILED_TIMEOUT_SECONDS", "240", minimum=1)

    @property
    def LLM_SUMMARY_INPUT_CHAR_BUDGET(self) -> int:
        """Option A (F-4.5-50, labeled-interim): the normalized transcript is TRUNCATED to this many chars
        before the summary call. K2-Think-v2 (reasoning) over a full real lecture (~46KB / ~11.6K tokens)
        exceeds the provider's server-side request timeout → HTTP 408 on BOTH routes; context-window fitting
        does not help (it fits the window; the wall is processing TIME). Empirically: 16KB (~4K tok) = 145s OK,
        8KB (~2K tok) = 90s OK, full 47KB = 408. 12000 (~3K tok, ~115s detailed) leaves margin under the
        ceiling. Truncation is LABELED on the summary record + surfaced in the UI — never silent. Full coverage
        of over-budget transcripts is map-reduce = F-4.5-51 (own spec, out of Stage 4.5)."""
        return self._int("LLM_SUMMARY_INPUT_CHAR_BUDGET", "12000", minimum=1)

    # ─── map-reduce summarization (Stage 4.5.1, F-4.5-51) ────────────────────
    # Removes the single-call size ceiling: the transcript is PARTITIONED into consecutive map-units
    # each under BOTH a char and an estimated-token budget, each summarized in its own (background)
    # call, then REDUCED into one coherent detailed summary. Budgets are HEADROOM under the empirical
    # 115–145s provider ceiling (8K≈90s comfortable; 12K≈115s = zero margin), NOT the last passing value.
    @property
    def LLM_SUMMARY_MAP_UNIT_CHAR_BUDGET(self) -> int:
        """Max chars of normalized transcript per map-unit. Partition packs the FEWEST consecutive
        segments under this (and the token budget); never splits a segment."""
        return self._int("LLM_SUMMARY_MAP_UNIT_CHAR_BUDGET", "9000", minimum=1)

    @property
    def LLM_SUMMARY_MAP_UNIT_TOKEN_BUDGET(self) -> int:
        """Max ESTIMATED prompt tokens (D2 chars/3.5) per map-unit — the second cap, so a dense unit
        that fits the char budget but not the token budget is still split."""
        return self._int("LLM_SUMMARY_MAP_UNIT_TOKEN_BUDGET", "2200", minimum=1)

    @property
    def LLM_SUMMARY_REDUCE_INPUT_CHAR_BUDGET(self) -> int:
        """§3.3 C1 guard threshold: if the serialized map partials exceed this, reduce runs TIERED
        (ordered groups → group-summaries → reduce those) instead of one call — the reduce input is
        itself a 408 surface and must never be assumed small."""
        return self._int("LLM_SUMMARY_REDUCE_INPUT_CHAR_BUDGET", "9000", minimum=1)

    @property
    def LLM_SUMMARY_REDUCE_INPUT_TOKEN_BUDGET(self) -> int:
        """Estimated-token companion to the reduce-input char budget (same guard, token axis)."""
        return self._int("LLM_SUMMARY_REDUCE_INPUT_TOKEN_BUDGET", "2200", minimum=1)

    @property
    def LLM_SUMMARY_MAX_MAP_UNITS(self) -> int:
        """Cost guard: a partition exceeding this many units fails LOUD rather than firing an absurd
        number of background calls. SINGLE source of truth — it is BOTH the partition cap AND the input
        to the detailed job's RQ timeout scaling (queues.py): raising it raises the timeout ceiling in
        lock-step, so the two can never drift (a sequential N-call job keeping the single-call timeout is
        the same work-horse SIGKILL we already hit once)."""
        return self._int("LLM_SUMMARY_MAX_MAP_UNITS", "20", minimum=1)

    @property
    def LLM_SUMMARY_MAP_CONCURRENCY(self) -> int:
        """Map calls run SEQUENTIALLY by default (1): cheapest on the shared background limiter and
        keeps ordering trivial. Hard-capped at 2 — higher would contend with interactive headroom."""
        value = self._int("LLM_SUMMARY_MAP_CONCURRENCY", "1", minimum=1)
        if value > 2:
            raise SettingsError("LLM_SUMMARY_MAP_CONCURRENCY must be between 1 and 2")
        return value

    @property
    def LLM_SUMMARY_INVALID_OUTPUT_RETRIES(self) -> int:
        """In-call retries for an ``invalid_output`` on a map/reduce gateway call (4.5.1c). K2-Think-v2 is
        a reasoning model and is non-deterministic: even with JSON mode a call can occasionally return an
        unparseable body. Each map unit / reduce call retries up to this many times WITHIN the job (no
        reliance on the absent RQ scheduler — F-4.5-47) before the job fails. Defense in depth on top of
        JSON mode + the hardened prompt."""
        return self._int("LLM_SUMMARY_INVALID_OUTPUT_RETRIES", "2", minimum=0)

    @property
    def LLM_DETAILED_MAP_REDUCE_CEILING_SECONDS(self) -> int:
        """Wall-clock CEILING for the map-reduce detailed summary: up to MAX_MAP_UNITS sequential map calls
        + a bounded tiered reduce (≤ MAP_UNITS reduce calls across tiers), each capped at the detailed HTTP
        timeout, + a buffer. SINGLE source of truth scaling with MAX_MAP_UNITS (the SAME setting the
        partition cost-guard reads) so the RQ work-horse ``job_timeout`` (queues.py) AND the stuck-row
        reaper threshold (recovery/reaper.py) move in LOCK-STEP with the partition cap — raising the cap
        raises both, never a stale flat number. A ceiling, not the expected run (a real ~60-min lecture is
        ~9 units, ~20 min). F-4.5.1a-3."""
        return 2 * self.LLM_SUMMARY_MAX_MAP_UNITS * self.LLM_DETAILED_TIMEOUT_SECONDS + 120

    @property
    def LLM_CONTEXT_FALLBACK_ENABLED(self) -> bool:
        """Whether ContextBuilder may fall back brief Cerebras→Nvidia on over-context (§12, adr-025).

        Default TRUE preserves 4.5a routing. The single-model 4.5b deviation sets this FALSE: the two
        routes are NOT proven to share a context window, so an over-limit prompt becomes invalid_input
        rather than silently rerouting. The fallback mechanism stays in code, dormant (F-4.5-37)."""
        return self._bool("LLM_CONTEXT_FALLBACK_ENABLED", default=True)

    # ─── rate_limited in-call backoff budgets (rule 15 / §10) ────────────────
    @property
    def LLM_RATE_LIMIT_MAX_BACKOFFS(self) -> int:
        """Max in-call backoffs (limiter-full waits + provider 429s) within ONE gateway attempt
        before it terminates as rate_limited. Bounds the loop; not an RQ retry."""
        return self._int("LLM_RATE_LIMIT_MAX_BACKOFFS", "4", minimum=0)

    @property
    def LLM_RATE_LIMIT_BASE_DELAY_MS(self) -> int:
        return self._int("LLM_RATE_LIMIT_BASE_DELAY_MS", "500", minimum=1)

    @property
    def LLM_RATE_LIMIT_MAX_DELAY_MS(self) -> int:
        return self._int("LLM_RATE_LIMIT_MAX_DELAY_MS", "8000", minimum=1)

    @property
    def LLM_RATE_LIMIT_MAX_ELAPSED_MS(self) -> int:
        """Cap on total in-call backoff wall-clock before terminal rate_limited."""
        return self._int("LLM_RATE_LIMIT_MAX_ELAPSED_MS", "30000", minimum=1)

    @property
    def LLM_BRIEF_MODEL_ID(self) -> str:
        # 4.5b deviation (ADR-025): the intended brief model `K2-V2-Instruct` (Cerebras) is not yet
        # accessible; only `K2-Think-v2` is verified. Kept in sync with prompts/brief_summary/v1.yaml
        # so the model SENT, the routed fit model, and the logged provenance all name one model.
        # Reverts to K2-V2-Instruct on access (ADR-025 switch-back; config + prompt-version bump).
        return os.environ.get("LLM_BRIEF_MODEL_ID", "MBZUAI-IFM/K2-Think-v2")

    @property
    def LLM_DETAILED_MODEL_ID(self) -> str:
        # 4.5c deviation (ADR-025, Option A): the intended detailed model `K2-Think-v0` (Nvidia) is
        # not yet accessible; detailed runs on the verified `K2-Think-v2` via the Nvidia route
        # (metadata.use_nvidia). Kept in sync with prompts/detailed_summary/v1.yaml so the model sent,
        # the routed fit model, and the logged provenance all name one model. Reverts to K2-Think-v0
        # on access (ADR-025 switch-back; prompt-version bump, detailed route already use_nvidia).
        return os.environ.get("LLM_DETAILED_MODEL_ID", "MBZUAI-IFM/K2-Think-v2")

    @property
    def LLM_CEREBRAS_CONTEXT_WINDOW_TOKENS(self) -> int:
        return self._int("LLM_CEREBRAS_CONTEXT_WINDOW_TOKENS", "32768", minimum=1)

    @property
    def LLM_NVIDIA_CONTEXT_WINDOW_TOKENS(self) -> int:
        return self._int("LLM_NVIDIA_CONTEXT_WINDOW_TOKENS", "131072", minimum=1)

    @property
    def LLM_CEREBRAS_RPM(self) -> int:
        return self._int("LLM_CEREBRAS_RPM", "20", minimum=1)

    @property
    def LLM_CEREBRAS_TPM(self) -> int:
        return self._int("LLM_CEREBRAS_TPM", "100000", minimum=1)

    @property
    def LLM_CEREBRAS_CONCURRENCY(self) -> int:
        return self._int("LLM_CEREBRAS_CONCURRENCY", "10", minimum=1)

    @property
    def LLM_NVIDIA_RPM(self) -> int:
        return self._int("LLM_NVIDIA_RPM", "10", minimum=1)

    @property
    def LLM_NVIDIA_TPM(self) -> int:
        return self._int("LLM_NVIDIA_TPM", "105000", minimum=1)

    @property
    def LLM_NVIDIA_CONCURRENCY(self) -> int:
        return self._int("LLM_NVIDIA_CONCURRENCY", "10", minimum=1)

    @property
    def LLM_INTERACTIVE_HEADROOM_PERCENT(self) -> int:
        value = self._int("LLM_INTERACTIVE_HEADROOM_PERCENT", "20", minimum=0)
        if value > 100:
            raise SettingsError("LLM_INTERACTIVE_HEADROOM_PERCENT must be between 0 and 100")
        return value

    @property
    def LLM_LEASE_TTL_SECONDS(self) -> int:
        """Concurrency-lease TTL; a crashed worker's slot is reclaimable after this. Must stay >= the
        longest request timeout (LLM_DETAILED_TIMEOUT_SECONDS) so a legitimate long detailed/reasoning
        call is not reclaimed mid-flight in the gateway path (F-4.5-49). Raised 120→300 with the
        detailed timeout; the smoke calls the provider directly and does not use the lease."""
        return self._int("LLM_LEASE_TTL_SECONDS", "300", minimum=1)

    def _bool(self, name: str, *, default: bool) -> bool:
        raw_value = os.environ.get(name)
        if raw_value is None or raw_value == "":
            return default
        normalized = raw_value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        raise SettingsError(f"{name} must be a boolean (true/false)")

    def _int(self, name: str, default: str, *, minimum: int) -> int:
        raw_value = os.environ.get(name, default)
        try:
            value = int(raw_value)
        except ValueError as exc:
            raise SettingsError(f"{name} must be an integer") from exc
        if value < minimum:
            raise SettingsError(f"{name} must be >= {minimum}")
        return value

    def _required(self, name: str) -> str:
        value = os.environ.get(name)
        if not value:
            raise SettingsError(f"{name} environment variable is required")
        return value


settings = Settings()
