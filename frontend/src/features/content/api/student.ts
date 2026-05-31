import type { AssetDownloadUrl } from "../../../lib/api/models/AssetDownloadUrl";
import type { SectionListItem } from "../../../lib/api/models/SectionListItem";
import type { StudentSectionDetail } from "../../../lib/api/models/StudentSectionDetail";
import { ContentService } from "../../../lib/api/services/ContentService";

export function listModuleSections(
  moduleId: string,
  authorization?: string,
): Promise<SectionListItem[]> {
  return ContentService.listSectionsModulesModuleIdSectionsGet(
    moduleId,
    authorization,
  );
}

export function getModuleSection(
  moduleId: string,
  sectionId: string,
  authorization?: string,
): Promise<StudentSectionDetail> {
  return ContentService.getSectionModulesModuleIdSectionsSectionIdGet(
    moduleId,
    sectionId,
    authorization,
  ) as Promise<StudentSectionDetail>;
}

export function createAssetDownloadUrl(
  moduleId: string,
  sectionId: string,
  assetId: string,
  authorization?: string,
): Promise<AssetDownloadUrl> {
  return ContentService.getAssetDownloadUrlModulesModuleIdSectionsSectionIdAssetsAssetIdDownloadUrlGet(
    moduleId,
    sectionId,
    assetId,
    authorization,
  );
}
