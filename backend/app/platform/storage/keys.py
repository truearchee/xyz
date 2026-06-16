from uuid import UUID, uuid4


def generate_section_asset_storage_key(
    *,
    module_id: UUID,
    section_id: UUID,
    asset_id: UUID,
    extension: str = ".pdf",
) -> str:
    nonce = uuid4().hex
    normalized_extension = extension.lower()
    if not normalized_extension.startswith("."):
        normalized_extension = f".{normalized_extension}"
    return (
        f"modules/{module_id}/sections/{section_id}/assets/"
        f"{asset_id}/{nonce}{normalized_extension}"
    )


def generate_transcript_storage_key(
    *,
    module_id: UUID,
    section_id: UUID,
    transcript_id: UUID,
    safe_file_name: str,
) -> str:
    return (
        f"modules/{module_id}/sections/{section_id}/transcripts/"
        f"{transcript_id}/{safe_file_name}"
    )
