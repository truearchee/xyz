import type { SectionAssetListResponse } from "../../../lib/api/models/SectionAssetListResponse";
import { ContentService } from "../../../lib/api/services/ContentService";

export function listSectionAssets(
  moduleId: string,
  sectionId: string,
  authorization?: string,
): Promise<SectionAssetListResponse> {
  return ContentService.listAssetsModulesModuleIdSectionsSectionIdAssetsGet(
    moduleId,
    sectionId,
    authorization,
  );
}
