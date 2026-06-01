import type { TranscriptMeta } from "../../../lib/api/models/TranscriptMeta";
import { TranscriptsService } from "../../../lib/api/services/TranscriptsService";

export function getSectionTranscript(
  moduleId: string,
  sectionId: string,
  authorization?: string,
): Promise<TranscriptMeta> {
  return TranscriptsService.getSectionTranscript(moduleId, sectionId, authorization);
}

export function uploadSectionTranscript(
  moduleId: string,
  sectionId: string,
  file: File,
  authorization?: string,
): Promise<TranscriptMeta> {
  return TranscriptsService.uploadSectionTranscript(
    moduleId,
    sectionId,
    { file },
    authorization,
  );
}
