import type { SectionAssetListResponse } from "../../../lib/api/models/SectionAssetListResponse";
import type { SectionAssetResponse } from "../../../lib/api/models/SectionAssetResponse";
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

export function uploadSectionAsset(
  moduleId: string,
  sectionId: string,
  file: File,
  authorization?: string,
): Promise<SectionAssetResponse> {
  return ContentService.uploadAssetModulesModuleIdSectionsSectionIdAssetsPost(
    moduleId,
    sectionId,
    { file },
    authorization,
  );
}

export function replaceSectionAsset(
  moduleId: string,
  sectionId: string,
  assetId: string,
  file: File,
  authorization?: string,
): Promise<SectionAssetResponse> {
  return ContentService.replaceAssetModulesModuleIdSectionsSectionIdAssetsAssetIdPut(
    moduleId,
    sectionId,
    assetId,
    { file },
    authorization,
  );
}
