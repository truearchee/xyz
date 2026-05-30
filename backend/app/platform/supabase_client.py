from supabase import AsyncClient, acreate_client

from app.platform.config import settings


_supabase_admin_client: AsyncClient | None = None


async def get_supabase_admin_client() -> AsyncClient:
    global _supabase_admin_client

    if _supabase_admin_client is None:
        _supabase_admin_client = await acreate_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SECRET_KEY,
        )
    return _supabase_admin_client
