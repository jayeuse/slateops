"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  catalogFirstPageOptions,
  departmentsOptions,
} from "../adapters/openview-queries";
import type { MappableModule } from "../domain/sheet-template";

/** A module the person can read, named "Module · Department" in choices. */
export type SheetModule = MappableModule & { titleFieldId: string | null };

/**
 * The modules the person can read, with their departments' names: link
 * columns of templates and data files map to them (X6), and a new sheet can
 * go on one (X7).
 */
export function useSheetModules(): {
  modules: SheetModule[];
  loading: boolean;
  failed: boolean;
  retry: () => void;
} {
  const catalog = useQuery(catalogFirstPageOptions());
  const departments = useQuery(departmentsOptions());
  const modules = useMemo(() => {
    const names = new Map(
      (departments.data?.items ?? []).map((item) => [item.id, item.name]),
    );
    return (catalog.data?.items ?? []).map((item) => ({
      id: item.id,
      name: item.name,
      departmentName: names.get(item.departmentId) ?? "",
      titleFieldId: item.titleFieldId,
    }));
  }, [catalog.data, departments.data]);
  return {
    modules,
    loading: catalog.isPending || departments.isPending,
    failed: catalog.isError,
    retry: () => {
      void catalog.refetch();
      void departments.refetch();
    },
  };
}

/** "Contacts · Sales", or the module's name alone. */
export function moduleLabel(module: MappableModule): string {
  return module.departmentName
    ? `${module.name} · ${module.departmentName}`
    : module.name;
}
