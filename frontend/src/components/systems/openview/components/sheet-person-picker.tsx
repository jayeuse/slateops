"use client";

import { useQuery } from "@tanstack/react-query";

import { worksheetKeys } from "../adapters/worksheet-queries";
import { searchWorksheetPeople } from "../adapters/worksheets-api";
import {
  PickerFrame,
  pickerStatus,
  useDelayedSearch,
} from "./sheet-link-picker";

// A person cell's picker (docs/specs/sheets.md, the people route): up to 20
// active members the editor can see, the editor included. The server checks
// the person again when the cell is saved.

export default function SheetPersonPicker({
  sheetId,
  columnName,
  hasPerson,
  onPick,
  onClose,
}: {
  sheetId: string;
  columnName: string;
  hasPerson: boolean;
  onPick: (personId: string | null, name: string) => void;
  onClose: () => void;
}) {
  const { typed, setTyped, search, searching } = useDelayedSearch();
  const people = useQuery({
    queryKey: [...worksheetKeys.detail(sheetId), "people", search],
    queryFn: ({ signal }) => searchWorksheetPeople(sheetId, search, signal),
  });
  const items = people.data ?? [];
  return (
    <PickerFrame
      title={`Choose ${columnName}`}
      description="Only people you can see in this organization."
      searchLabel="Search people"
      typed={typed}
      onType={setTyped}
      choices={items.map((person) => ({
        id: person.id,
        label: person.displayName,
        onChoose: () => onPick(person.id, person.displayName),
      }))}
      status={pickerStatus({
        searching: searching || people.isPending,
        empty: people.isSuccess && items.length === 0,
        failed: people.isError,
        noMatch: "No people match.",
        failure: "People could not be listed.",
      })}
      removeLabel={hasPerson ? "Remove person" : null}
      onRemove={() => onPick(null, "")}
      onClose={onClose}
    />
  );
}
