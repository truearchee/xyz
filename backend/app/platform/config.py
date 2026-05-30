import os


class SettingsError(RuntimeError):
    pass


class Settings:
    @property
    def SUPABASE_URL(self) -> str:
        return self._required("SUPABASE_URL")

    @property
    def SUPABASE_SECRET_KEY(self) -> str:
        return self._required("SUPABASE_SECRET_KEY")

    @property
    def SUPABASE_JWKS_URL(self) -> str:
        return self._required("SUPABASE_JWKS_URL")

    @property
    def SUPABASE_JWT_AUDIENCE(self) -> str:
        return os.environ.get("SUPABASE_JWT_AUDIENCE", "authenticated")

    @property
    def SUPABASE_JWT_ISSUER(self) -> str:
        return self._required("SUPABASE_JWT_ISSUER")

    def _required(self, name: str) -> str:
        value = os.environ.get(name)
        if not value:
            raise SettingsError(f"{name} environment variable is required")
        return value


settings = Settings()
