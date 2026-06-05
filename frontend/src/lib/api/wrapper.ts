'use client';

import { ContentService, MeService, ModulesService, OpenAPI } from './index';
import { getSupabaseBrowserClient } from '../supabase/client';

OpenAPI.BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

OpenAPI.TOKEN = async () => {
  const supabase = getSupabaseBrowserClient();
  const { data, error } = await supabase.auth.getSession();
  if (error) {
    throw error;
  }

  return data.session?.access_token ?? '';
};

export const api = {
  content: {
    getAssetDownloadUrl: (moduleId: string, sectionId: string, assetId: string) =>
      ContentService.getAssetDownloadUrlModulesModuleIdSectionsSectionIdAssetsAssetIdDownloadUrlGet(
        moduleId,
        sectionId,
        assetId,
      ),
    getSection: (moduleId: string, sectionId: string) =>
      ContentService.getSectionModulesModuleIdSectionsSectionIdGet(
        moduleId,
        sectionId,
      ),
    listSections: (moduleId: string) =>
      ContentService.listSectionsModulesModuleIdSectionsGet(moduleId),
    publishSection: (moduleId: string, sectionId: string) =>
      ContentService.publishModulesModuleIdSectionsSectionIdPublishPost(
        moduleId,
        sectionId,
      ),
    uploadAsset: (moduleId: string, sectionId: string, file: File) =>
      ContentService.uploadAssetModulesModuleIdSectionsSectionIdAssetsPost(
        moduleId,
        sectionId,
        { file },
      ),
  },
  me: {
    get: () => MeService.getMeMeGet(),
  },
  modules: {
    list: () => ModulesService.listModulesModulesGet(),
  },
};
