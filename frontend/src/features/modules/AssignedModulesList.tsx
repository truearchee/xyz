"use client";

import { useCallback, useEffect, useState } from "react";

import type { ModuleSummary } from "../../lib/api";
import { api } from "../../lib/api/wrapper";
import { ModuleListView } from "./ModuleListView";

type AssignedModulesListProps = {
  moduleHrefPrefix?: string;
};

export function AssignedModulesList({ moduleHrefPrefix }: AssignedModulesListProps) {
  const [modules, setModules] = useState<ModuleSummary[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadModules = useCallback(async () => {
    setErrorMessage(null);
    try {
      setModules(await api.modules.list());
    } catch (caught) {
      setErrorMessage(caught instanceof Error ? caught.message : "Unable to load modules");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadModules();
  }, [loadModules]);

  return (
    <ModuleListView
      errorMessage={errorMessage}
      getModuleHref={
        moduleHrefPrefix
          ? (module) => `${moduleHrefPrefix}/${module.id}`
          : () => "#"
      }
      isLoading={isLoading}
      modules={modules}
    />
  );
}
