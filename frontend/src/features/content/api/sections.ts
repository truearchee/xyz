import type { SectionDetail } from "../../../lib/api/models/SectionDetail";
import { ContentService } from "../../../lib/api/services/ContentService";

export function publishSection(
  moduleId: string,
  sectionId: string,
  authorization?: string,
): Promise<SectionDetail> {
  return ContentService.publishModulesModuleIdSectionsSectionIdPublishPost(
    moduleId,
    sectionId,
    authorization,
  );
}

export function unpublishSection(
  moduleId: string,
  sectionId: string,
  authorization?: string,
): Promise<SectionDetail> {
  return ContentService.unpublishModulesModuleIdSectionsSectionIdUnpublishPost(
    moduleId,
    sectionId,
    authorization,
  );
}

export function updateSectionNotes(
  moduleId: string,
  sectionId: string,
  lecturerNotes: string | null,
  authorization?: string,
): Promise<SectionDetail> {
  return ContentService.updateNotesModulesModuleIdSectionsSectionIdNotesPatch(
    moduleId,
    sectionId,
    { lecturerNotes },
    authorization,
  );
}
