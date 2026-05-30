from uuid import UUID, uuid4


def generate_section_asset_storage_key(
    *,
    module_id: UUID,
    section_id: UUID,
    asset_id: UUID,
) -> str:
    nonce = uuid4().hex
    return f"modules/{module_id}/sections/{section_id}/assets/{asset_id}/{nonce}.pdf"
