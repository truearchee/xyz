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
    def REDIS_URL(self) -> str:
        return os.environ.get("REDIS_URL", "redis://redis:6379/0")

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
        """Ask the provider for ``response_format={"type":"json_object"}`` (§7.1). Default OFF until
        the 4.5b smoke confirms K2-Think-v2 honors it (an unsupported param could 400). The §7
        tolerant-extract validator is the safety net regardless."""
        return self._bool("LLM_PROVIDER_JSON_MODE", default=False)

    @property
    def LLM_PROVIDER_TIMEOUT_SECONDS(self) -> int:
        """HTTP transport timeout for the real provider; a timeout maps to provider_transient (§8)."""
        return self._int("LLM_PROVIDER_TIMEOUT_SECONDS", "60", minimum=1)

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
        """Concurrency-lease TTL; a crashed worker's slot is reclaimable after this."""
        return self._int("LLM_LEASE_TTL_SECONDS", "120", minimum=1)

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
