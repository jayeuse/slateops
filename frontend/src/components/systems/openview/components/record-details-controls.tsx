"use client";

import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useReducer,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { MoreHorizontal, Pencil } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getApiFieldErrors } from "@/lib/api";
import { apiErrorMessage } from "@/lib/api-errors";
import { lifecycleErrorMessage } from "@/lib/lifecycle";
import { LifecyclePurgeReview } from "@/components/systems/shared/lifecycle-purge-review";
import { authMeOptions } from "../adapters/openview-queries";
import {
  subscribeWorkspaceLifecycleSettings,
  workspaceLifecycleQueryOptions,
  workspaceCalendarQueryOptions,
} from "../../manage/adapters/workspace-api";
import type {
  OpenViewDataSourceField,
  OpenViewRecord,
} from "../adapters/views-api";
import {
  deleteOpenViewRecord,
  getOpenViewRecord,
  isStaleRecordSave,
  previewRecordPurge,
  purgeRecord,
  restoreOpenViewRecord,
  updateOpenViewRecord,
} from "../adapters/records-api";
import type { LifecyclePurgePreview } from "@/lib/lifecycle";
import {
  encodeRecordForm,
  initialFormValues,
  serverFieldMessage,
  toFormValue,
  type RecordFormErrors,
  type RecordFormValue,
  type RecordFormValues,
} from "../domain/record-form";
import {
  canStartInPlace,
  DELETE_UNDO_WORDS,
  deleteUndoFailure,
  inPlaceChangeMessage,
  inPlaceCommit,
  inPlaceFailure,
  inPlaceMode,
  inPlacePatchData,
  inPlaceReducer,
  inPlaceStatus,
  initialInPlaceState,
  seenRecord,
  type RecordInPlaceStatus,
} from "../domain/record-inplace-change";
import { formatOpenViewFieldValue } from "./live-record-cards";
import { RecordFormFields } from "./record-form-fields";
import { RecordInPlaceField } from "./record-inplace-field";
import type { WorkspaceRegion } from "@/lib/date-time";
import { Alert } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useErrorText } from "@/lib/use-error-text";

type Editing = {
  /** The complete stored record the form started from. */
  source: OpenViewRecord;
  /** The complete field catalog that owns this editing draft. */
  fields: readonly OpenViewDataSourceField[];
  values: RecordFormValues;
  errors: RecordFormErrors;
  stale: boolean;
};

/** The OpenView sheet's opt-in to change values in place (item 2, DR-2.12). */
export type RecordInPlaceOptions = {
  region: WorkspaceRegion | undefined;
  /** The Details tab is the open tab; leaving it ends the Undo offer. */
  detailsActive: boolean;
  /** The open tab; any tab change ends a delete's Undo (DR-SI-9.4). */
  tab: string;
  /** The record header's status: "Saving…", the change with Undo, a refusal. */
  onStatus: (status: RecordInPlaceStatus | null) => void;
  /** The Details rows, with the in-place control of a row where one fits. */
  renderDetails: (
    valueFor: (field: OpenViewDataSourceField, labelId: string) => ReactNode,
  ) => ReactNode;
};

type RecordDetailsControlsProps = {
  record: OpenViewRecord;
  moduleId: string;
  /** Every active field of the record's module, in order. */
  fields: readonly OpenViewDataSourceField[];
  canWrite: boolean;
  fieldsHasMore?: boolean;
  fieldsLoadingMore?: boolean;
  onLoadMoreFields?: () => void;
  /** The read-only field list. */
  children: ReactNode;
  onChanged: (message: string) => void;
  /** Reports whether the edit form is open, so the dialog can guard it. */
  onEditingChange?: (editing: boolean) => void;
  /** The sheet header's place for Edit and the record menu (OD7). */
  actionsSlot: HTMLElement | null;
  /** Items the record menu always holds (Copy link). */
  menuItems: ReactNode;
  /** Shows the Details tab, where the Edit form opens (DR-2.1). */
  onShowDetails?: () => void;
  /** Values change in place on Details; off unless the sheet opts in. */
  inPlace?: RecordInPlaceOptions;
  /**
   * Delete record deletes at once, with "Record deleted." and Undo in the
   * header status (SI-9.1, DR-SI-9.1). It needs `inPlace`, whose status the
   * header shows; without it, or unset, Delete asks first (SI-9.5).
   */
  deleteWithUndo?: boolean;
};

/** A delete's header status and its Undo (DR-SI-9.2 to DR-SI-9.4). */
type DeleteNotice =
  | { kind: "deleted" }
  | { kind: "restoring" }
  | { kind: "settled"; message: string }
  | { kind: "gone" }
  | { kind: "failed"; message: string; reference: string | undefined };

/** Focuses after React renders the next state. */
function focusSoon(find: () => HTMLElement | null | undefined) {
  requestAnimationFrame(() => find()?.focus());
}

function fieldErrors(
  error: unknown,
  fields: readonly OpenViewDataSourceField[],
): RecordFormErrors {
  const known = new Set(fields.map((field) => field.id));
  return Object.fromEntries(
    Object.entries(getApiFieldErrors(error))
      .filter(([fieldId]) => known.has(fieldId))
      .map(([fieldId, messages]) => [
        fieldId,
        serverFieldMessage(messages[0] ?? ""),
      ]),
  );
}

/** The Details tab: read-only values, or the edit form, and lifecycle actions. */
export function RecordDetailsControls({
  record,
  moduleId,
  fields,
  canWrite,
  fieldsHasMore = false,
  fieldsLoadingMore = false,
  onLoadMoreFields,
  children,
  onChanged,
  onEditingChange,
  actionsSlot,
  menuItems,
  onShowDetails,
  inPlace,
  deleteWithUndo = false,
}: RecordDetailsControlsProps) {
  const [editing, setEditing] = useState<Editing | null>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const editButtonRef = useRef<HTMLButtonElement>(null);
  const moreActionsRef = useRef<HTMLButtonElement>(null);
  const undoDeleteMode = deleteWithUndo && inPlace !== undefined;
  const [deleteNotice, setDeleteNotice] = useState<DeleteNotice | null>(null);
  // Any tab change ends a delete's Undo and its words (DR-SI-9.4, G8).
  const openTab = inPlace?.tab;
  const [wasOpenTab, setWasOpenTab] = useState(openTab);
  if (wasOpenTab !== openTab) {
    setWasOpenTab(openTab);
    setDeleteNotice(null);
  }
  const id = useId();
  const identity = useQuery(authMeOptions());
  const isAdmin = identity.data?.role === "admin";
  const client = useQueryClient();
  const workspace = useQuery({
    ...workspaceLifecycleQueryOptions(),
    enabled: isAdmin && record.isDeleted,
  });
  const region = useQuery({
    ...workspaceCalendarQueryOptions(),
    enabled: isAdmin && record.isDeleted,
  });
  const canPurge =
    isAdmin &&
    record.isDeleted &&
    workspace.isSuccess &&
    workspace.data.purge_enabled;
  useEffect(() => {
    if (isAdmin && record.isDeleted)
      return subscribeWorkspaceLifecycleSettings(client);
  }, [client, isAdmin, record.isDeleted]);
  const isEditing = editing !== null;
  useEffect(() => {
    onEditingChange?.(isEditing);
  }, [isEditing, onEditingChange]);
  useEffect(() => () => onEditingChange?.(false), [onEditingChange]);
  const focusFirstInvalid = () =>
    focusSoon(() =>
      formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]'),
    );
  const focusEditButton = () => focusSoon(() => editButtonRef.current);
  const [pending, setPending] = useState<
    | "open"
    | "save"
    | "in-place"
    | "delete"
    | "restore"
    | "reload"
    | "purge-preview"
    | "purge"
    | null
  >(null);
  const [errorFailure, setError] = useErrorText();
  const error = errorFailure?.message ?? "";
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [purgePreview, setPurgePreview] =
    useState<LifecyclePurgePreview | null>(null);
  const [purgeConfirmationName, setPurgeConfirmationName] = useState("");
  const [purgePassword, setPurgePassword] = useState("");
  const [purgeReviewAgain, setPurgeReviewAgain] = useState(false);
  const busy = pending !== null;
  useEffect(() => {
    if (canPurge) return;
    setPurgePreview(null);
    setPurgeConfirmationName("");
    setPurgePassword("");
    setPurgeReviewAgain(false);
  }, [canPurge]);

  // In place (DR-2.2 to DR-2.13): one session per record; a ref lock stops
  // the Enter and blur of one date from committing twice in one tick.
  const [inPlaceState, dispatchInPlace] = useReducer(
    inPlaceReducer,
    initialInPlaceState,
  );
  // Each settled commit starts a new draft in the controls.
  const [inPlaceSettled, setInPlaceSettled] = useState(0);
  const inPlaceLock = useRef(false);
  // Locked in-place controls dim only when the wait runs past 300 ms (G2).
  const [lockLong, setLockLong] = useState(false);
  useEffect(() => {
    if (!busy) return;
    const timer = window.setTimeout(() => setLockLong(true), 300);
    return () => window.clearTimeout(timer);
  }, [busy]);
  if (!busy && lockLong) setLockLong(false);
  const undoRef = useRef<() => void>(() => undefined);
  const undo = useCallback(() => undoRef.current(), []);
  // Leaving the Details tab ends the Undo offer (DR-2.6).
  const detailsActive = inPlace?.detailsActive ?? true;
  const [wasDetailsActive, setWasDetailsActive] = useState(detailsActive);
  if (wasDetailsActive !== detailsActive) {
    setWasDetailsActive(detailsActive);
    if (!detailsActive) dispatchInPlace({ type: "clear-status" });
  }
  // A commit, the header's Undo included, needs the complete catalog and a
  // writable record; otherwise a PATCH would drop values (DR-2.13).
  const commitsOpen =
    canWrite &&
    !record.isDeleted &&
    editing === null &&
    !fieldsHasMore &&
    !fieldsLoadingMore;
  const statusData = inPlaceStatus(inPlaceState, commitsOpen);
  const statusKind = statusData?.kind ?? null;
  const statusMessage = statusData?.message ?? "";
  const statusReference =
    statusData?.kind === "failed" ? statusData.reference : undefined;
  const statusUndo = statusData?.kind === "saved" && statusData.canUndo;
  // The delete's Undo keeps one identity; it runs the latest restore rules.
  const undoDeleteRef = useRef<() => void>(() => undefined);
  const undoDelete = useCallback(() => undoDeleteRef.current(), []);
  // One object per status, so the page's state changes only when it does.
  const headerStatus = useMemo<RecordInPlaceStatus | null>(() => {
    // A delete supersedes the last in-place change, whose words it cleared.
    if (deleteNotice?.kind === "deleted" || deleteNotice?.kind === "restoring")
      return {
        kind: "deleted",
        message: DELETE_UNDO_WORDS.deleted,
        undo: deleteNotice.kind === "deleted" ? undoDelete : null,
      };
    if (deleteNotice?.kind === "settled")
      return { kind: "saved", message: deleteNotice.message, undo: null };
    if (deleteNotice?.kind === "gone")
      return { kind: "gone", message: DELETE_UNDO_WORDS.deletedForever };
    if (deleteNotice?.kind === "failed")
      return {
        kind: "failed",
        message: deleteNotice.message,
        reference: deleteNotice.reference,
      };
    if (statusKind === null) return null;
    if (statusKind === "saving")
      return { kind: "saving", message: statusMessage };
    if (statusKind === "failed")
      return {
        kind: "failed",
        message: statusMessage,
        reference: statusReference,
      };
    return {
      kind: "saved",
      message: statusMessage,
      undo: statusUndo ? undo : null,
    };
  }, [
    deleteNotice,
    undoDelete,
    statusKind,
    statusMessage,
    statusReference,
    statusUndo,
    undo,
  ]);
  const onInPlaceStatus = inPlace?.onStatus;
  useEffect(() => {
    onInPlaceStatus?.(headerStatus);
  }, [headerStatus, onInPlaceStatus]);
  useEffect(() => () => onInPlaceStatus?.(null), [onInPlaceStatus]);

  const startEditing = async (reload = false) => {
    if (fieldsHasMore || fieldsLoadingMore) return;
    if (!reload) {
      // DR-2.1: the form opens on Details, whichever tab is open.
      onShowDetails?.();
      dispatchInPlace({ type: "clear-status" });
      setDeleteNotice(null);
    }
    setPending(reload ? "reload" : "open");
    setError("");
    try {
      const source = await getOpenViewRecord(record.id);
      if (source.isDeleted) {
        setEditing(null);
        setError("This record was deleted. Restore it to change its values.");
        onChanged("");
        return;
      }
      setEditing({
        source,
        fields: [...fields],
        values: initialFormValues(fields, source.data),
        errors: {},
        stale: false,
      });
      if (!reload)
        focusSoon(() =>
          formRef.current?.querySelector<HTMLElement>(
            "input, select, textarea",
          ),
        );
    } catch (caught) {
      setError(
        apiErrorMessage(caught, "The record could not be opened for editing."),
        caught,
      );
    } finally {
      setPending(null);
    }
  };

  const save = async () => {
    if (!editing || busy || editing.stale || fieldsHasMore || fieldsLoadingMore)
      return;
    const { data, errors, changed } = encodeRecordForm(
      editing.fields,
      editing.values,
      editing.source.data,
    );
    if (Object.keys(errors).length > 0) {
      setEditing({ ...editing, errors });
      focusFirstInvalid();
      return;
    }
    if (!changed) {
      setEditing(null);
      focusEditButton();
      return;
    }
    setPending("save");
    setError("");
    try {
      await updateOpenViewRecord({
        recordId: record.id,
        revision: editing.source.updatedAt,
        data,
      });
      setEditing(null);
      onChanged("Record saved.");
      focusEditButton();
    } catch (caught) {
      if (isStaleRecordSave(caught)) {
        setEditing({ ...editing, errors: {}, stale: true });
      } else {
        const errors = fieldErrors(caught, editing.fields);
        setEditing({ ...editing, errors });
        if (Object.keys(errors).length > 0) focusFirstInvalid();
        if (Object.keys(errors).length === 0)
          setError(
            apiErrorMessage(caught, "The record could not be saved."),
            caught,
          );
      }
    } finally {
      setPending(null);
    }
  };

  const inPlaceControlId = (fieldId: string) => `${id}-in-place-${fieldId}`;

  const commitInPlace = async (
    field: OpenViewDataSourceField,
    value: unknown,
    isUndo: boolean,
  ) => {
    if (
      !commitsOpen ||
      busy ||
      inPlaceLock.current ||
      !canStartInPlace(inPlaceState)
    )
      return;
    inPlaceLock.current = true;
    // Undo removes its own button: focus goes to the field it changes back,
    // before the button leaves, so it never falls back to the sheet.
    if (isUndo)
      document
        .querySelector<HTMLElement>(
          `[data-in-place-field="${field.id}"] [aria-labelledby]`,
        )
        ?.focus();
    const seen = seenRecord(record, inPlaceState.latest);
    setDeleteNotice(null);
    dispatchInPlace({ type: "start", fieldId: field.id, value, undo: isUndo });
    setPending("in-place");
    setError("");
    try {
      // A list row holds only the view's columns; a PATCH replaces every
      // active value, so it starts from the complete stored record (DR-2.4).
      // Its If-Match stays the revision behind the value on screen.
      const source =
        seen === inPlaceState.latest
          ? seen
          : await getOpenViewRecord(record.id);
      const saved = await updateOpenViewRecord({
        recordId: record.id,
        revision: seen.updatedAt,
        data: inPlacePatchData(fields, source.data, field.id, value),
      });
      dispatchInPlace({
        type: "saved",
        record: saved,
        message: inPlaceChangeMessage(
          field,
          value,
          formatOpenViewFieldValue(value, field.type, inPlace?.region),
          isUndo,
        ),
        undo: isUndo
          ? null
          : { fieldId: field.id, previous: source.data[field.id] ?? null },
      });
      // The list row and the header's Updated date read the record again.
      onChanged("");
    } catch (caught) {
      const failure = inPlaceFailure(caught, field.id);
      let reread: OpenViewRecord | null = null;
      if (failure.kind === "conflict") {
        // DR-2.7: nothing is overwritten; the control shows the stored value.
        reread = await getOpenViewRecord(record.id).catch(() => null);
        onChanged("");
      }
      dispatchInPlace({ type: "refused", failure, record: reread });
    } finally {
      inPlaceLock.current = false;
      setPending(null);
      setInPlaceSettled((count) => count + 1);
    }
  };

  // The header's Undo keeps one identity; it runs the latest commit rules.
  useEffect(() => {
    undoRef.current = () => {
      const change = inPlaceState.undo;
      const field = change && fields.find((item) => item.id === change.fieldId);
      if (change && field) void commitInPlace(field, change.previous, true);
    };
  });

  const remove = async () => {
    if (busy) return;
    setPending("delete");
    setError("");
    // The delete is the next change: the last change's Undo goes (G8).
    if (undoDeleteMode) {
      dispatchInPlace({ type: "clear-status" });
      setDeleteNotice(null);
    }
    try {
      await deleteOpenViewRecord(record.id);
      setConfirmDelete(false);
      if (undoDeleteMode) {
        // DR-SI-9.2: the header says it with Undo; the page adds no notice.
        setDeleteNotice({ kind: "deleted" });
        onChanged("");
      } else onChanged("Record deleted. You can restore it from this dialog.");
    } catch (caught) {
      setConfirmDelete(false);
      setError(
        apiErrorMessage(caught, "The record could not be deleted."),
        caught,
      );
    } finally {
      setPending(null);
    }
  };

  // DR-SI-9.3: Undo restores the record; a refusal shows in the header and
  // the record stays deleted, with Restore.
  const restoreFromUndo = async () => {
    if (busy) return;
    // Undo leaves with its words: focus goes to the record menu first, so it
    // stays in the sheet (SI-9.2).
    moreActionsRef.current?.focus();
    setDeleteNotice({ kind: "restoring" });
    setPending("restore");
    setError("");
    try {
      await restoreOpenViewRecord(record.id);
      setDeleteNotice({ kind: "settled", message: DELETE_UNDO_WORDS.restored });
      onChanged("");
    } catch (caught) {
      const failure = deleteUndoFailure(caught, fields);
      if (failure.kind === "already-restored") {
        // The sheet reads the record again and shows it as it is now.
        setDeleteNotice({
          kind: "settled",
          message: DELETE_UNDO_WORDS.alreadyRestored,
        });
        onChanged("");
      } else if (failure.kind === "deleted-forever") {
        // The sheet reads again and shows "Record unavailable"; the page
        // keeps these words in the sheet header (G7).
        setDeleteNotice({ kind: "gone" });
        onChanged("");
      } else
        setDeleteNotice({
          kind: "failed",
          message: failure.message,
          reference: failure.kind === "failed" ? failure.reference : undefined,
        });
    } finally {
      setPending(null);
    }
  };
  useEffect(() => {
    undoDeleteRef.current = () => void restoreFromUndo();
  });

  const restore = async () => {
    // Restore ends a delete's Undo (DR-SI-9.4).
    setDeleteNotice(null);
    setPending("restore");
    setError("");
    try {
      await restoreOpenViewRecord(record.id);
      onChanged("Record restored.");
    } catch (caught) {
      setError(
        apiErrorMessage(caught, "The record could not be restored."),
        caught,
      );
    } finally {
      setPending(null);
    }
  };

  const clearPurgeReview = () => {
    setPurgePreview(null);
    setPurgeConfirmationName("");
    setPurgePassword("");
    setPurgeReviewAgain(false);
  };

  const beginPurgeReview = async () => {
    if (!canPurge || busy) return;
    setDeleteNotice(null);
    setPending("purge-preview");
    setError("");
    clearPurgeReview();
    try {
      const preview = await previewRecordPurge(record.id);
      setPurgePreview(preview);
      setPurgeReviewAgain(preview.impact.blockers.length > 0);
    } catch (caught) {
      setError(
        lifecycleErrorMessage(
          caught,
          "The Delete forever review could not be prepared. Try again.",
        ),
        caught,
      );
      setPurgeReviewAgain(true);
    } finally {
      setPending(null);
      setPurgePassword("");
    }
  };

  const confirmPurge = async () => {
    if (
      !canPurge ||
      !purgePreview ||
      purgePreview.impact.blockers.length > 0 ||
      purgeConfirmationName !== purgePreview.confirmation_name ||
      purgePassword.length === 0 ||
      busy
    )
      return;
    const password = purgePassword;
    setPending("purge");
    setError("");
    try {
      await purgeRecord(record.id, {
        token: purgePreview.token,
        confirmationName: purgePreview.confirmation_name,
        password,
      });
      clearPurgeReview();
      onChanged("Record deleted forever.");
    } catch (caught) {
      setError(
        lifecycleErrorMessage(
          caught,
          "Delete forever could not be confirmed. Request a new review and try again.",
        ),
        caught,
      );
      clearPurgeReview();
      setPurgeReviewAgain(true);
    } finally {
      setPurgePassword("");
      setPending(null);
    }
  };

  const editable = canWrite && !record.isDeleted;

  const inPlaceValue = (
    shownField: OpenViewDataSourceField,
    labelId: string,
  ): ReactNode => {
    // The catalog field carries the options and the required rule.
    const field = fields.find((item) => item.id === shownField.id);
    const mode = inPlaceMode(field, {
      canWrite,
      isDeleted: record.isDeleted,
      editing: editing !== null,
      fieldsComplete: !fieldsHasMore && !fieldsLoadingMore,
    });
    if (!field || mode === "plain") return null;
    const value = toFormValue(
      field,
      seenRecord(record, inPlaceState.latest).data[field.id],
    );
    const saving: RecordFormValue | null =
      inPlaceState.saving?.fieldId === field.id
        ? toFormValue(field, inPlaceState.saving.value)
        : null;
    return (
      <RecordInPlaceField
        key={field.id}
        id={inPlaceControlId(field.id)}
        moduleId={moduleId}
        field={field}
        labelId={labelId}
        value={value}
        saving={saving}
        disabled={mode === "waiting"}
        // While a commit runs, every control here waits without losing
        // focus (DR-2.4, DR-2.13).
        locked={busy}
        dimmed={busy && lockLong}
        settled={inPlaceSettled}
        error={
          inPlaceState.fieldError?.fieldId === field.id
            ? inPlaceState.fieldError
            : null
        }
        onCommit={(input, complete) => {
          const commit = inPlaceCommit(
            field,
            seenRecord(record, inPlaceState.latest).data[field.id],
            input,
            complete,
          );
          if (commit.kind === "commit")
            void commitInPlace(field, commit.value, false);
          // A value that cannot be saved puts back the stored value.
          else if (commit.kind === "revert")
            setInPlaceSettled((count) => count + 1);
        }}
      />
    );
  };
  const metadataGuard =
    editable && fieldsHasMore ? (
      <Alert
        role="note"
        className="flex flex-wrap items-center justify-between gap-2"
      >
        <span>
          {editing
            ? "Field metadata refreshed. Load all fields before saving; your changes are kept."
            : "Load all fields before editing so existing values are kept."}
        </span>
        <Button
          type="button"
          variant="outline"
          className="min-h-11"
          disabled={busy || fieldsLoadingMore}
          onClick={onLoadMoreFields}
        >
          {fieldsLoadingMore
            ? "Loading fields…"
            : "Load more fields for editing"}
        </Button>
      </Alert>
    ) : null;

  // OD7: a quiet Edit and the record menu sit in the sheet header; Delete is
  // in the menu. While the form is open they step aside.
  const headerActions = actionsSlot
    ? createPortal(
        <>
          {editable && !editing ? (
            <Button
              ref={editButtonRef}
              type="button"
              variant="outline"
              className="min-h-11"
              // While it opens, the visible "Opening…" is the name.
              aria-label={pending === "open" ? undefined : "Edit record"}
              disabled={busy || fieldsHasMore || fieldsLoadingMore}
              onClick={() => void startEditing()}
            >
              <Pencil aria-hidden="true" />
              {pending === "open" ? "Opening…" : "Edit"}
            </Button>
          ) : null}
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button
                  ref={moreActionsRef}
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-11"
                  aria-label="More record actions"
                />
              }
            >
              <MoreHorizontal aria-hidden="true" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="slim-ui min-w-48">
              {menuItems}
              {editable && !editing ? (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    variant="destructive"
                    className="min-h-11 xl:min-h-8"
                    disabled={busy}
                    // SI-9.1: the OpenView sheet deletes at once with Undo;
                    // the Boards card sheet asks first (SI-9.5).
                    onClick={() =>
                      undoDeleteMode ? void remove() : setConfirmDelete(true)
                    }
                  >
                    Delete record
                  </DropdownMenuItem>
                </>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>
        </>,
        actionsSlot,
      )
    : null;

  return (
    <div className="flex min-w-0 flex-col gap-4">
      {headerActions}
      {error ? (
        <Alert
          role="alert"
          variant="destructive"
          reference={errorFailure?.reference}
        >
          {error}
        </Alert>
      ) : null}
      {editing ? (
        <form
          ref={formRef}
          className="flex min-w-0 flex-col gap-4"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          {metadataGuard}
          {editing.stale ? (
            <Alert role="alert" variant="destructive">
              <p className="font-medium">
                This record changed after you opened it
              </p>
              <p className="mt-1">
                Your changes are not saved. Load the latest values, then make
                your changes again.
              </p>
              <Button
                type="button"
                variant="outline"
                className="mt-3 min-h-11"
                disabled={busy || fieldsHasMore || fieldsLoadingMore}
                onClick={() => void startEditing(true)}
              >
                {pending === "reload" ? "Loading…" : "Load latest values"}
              </Button>
            </Alert>
          ) : null}
          <RecordFormFields
            moduleId={moduleId}
            fields={editing.fields}
            values={editing.values}
            errors={editing.errors}
            disabled={busy}
            onChange={(fieldId, value) =>
              setEditing((current) =>
                current
                  ? {
                      ...current,
                      values: { ...current.values, [fieldId]: value },
                      errors: Object.fromEntries(
                        Object.entries(current.errors).filter(
                          ([id]) => id !== fieldId,
                        ),
                      ),
                    }
                  : current,
              )
            }
          />
          <div className="bg-card sticky bottom-0 z-10 flex flex-wrap gap-2 border-t py-3">
            <Button
              type="submit"
              className="min-h-11"
              disabled={
                busy || editing.stale || fieldsHasMore || fieldsLoadingMore
              }
            >
              {pending === "save" ? "Saving…" : "Save changes"}
            </Button>
            <Button
              type="button"
              variant="outline"
              className="min-h-11"
              disabled={busy}
              onClick={() => {
                setEditing(null);
                setError("");
                focusEditButton();
              }}
            >
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <>
          {metadataGuard}
          {record.isDeleted && (canWrite || isAdmin) ? (
            <div className="flex flex-wrap gap-2">
              {canWrite ? (
                <Button
                  type="button"
                  className="min-h-11"
                  disabled={busy}
                  onClick={() => void restore()}
                >
                  {pending === "restore" ? "Restoring…" : "Restore record"}
                </Button>
              ) : null}
              {canPurge ? (
                <Button
                  type="button"
                  variant="outline"
                  className="text-destructive min-h-11"
                  disabled={busy}
                  onClick={() => void beginPurgeReview()}
                >
                  {pending === "purge-preview"
                    ? "Preparing review…"
                    : purgeReviewAgain
                      ? "Review again"
                      : "Delete forever"}
                </Button>
              ) : null}
            </div>
          ) : null}
          {canPurge && purgePreview ? (
            <div className="border-border space-y-4 rounded-lg border p-4">
              <LifecyclePurgeReview
                preview={purgePreview}
                region={region.data}
              />
              {purgePreview.impact.blockers.length > 0 ? null : (
                <form
                  className="space-y-4"
                  onSubmit={(event: FormEvent<HTMLFormElement>) => {
                    event.preventDefault();
                    void confirmPurge();
                  }}
                >
                  <p className="text-sm" role="status">
                    Type the exact record name and enter your administrator
                    password to continue.
                  </p>
                  <p className="text-sm">
                    Record name:{" "}
                    <code className="break-all">
                      {purgePreview.confirmation_name}
                    </code>
                  </p>
                  <div className="space-y-2">
                    <label
                      htmlFor={`${id}-purge-confirmation`}
                      className="text-sm font-medium"
                    >
                      Type the record name
                    </label>
                    <input
                      id={`${id}-purge-confirmation`}
                      value={purgeConfirmationName}
                      autoComplete="off"
                      disabled={busy}
                      className="border-input bg-card text-foreground focus-visible:outline-ring min-h-11 w-full rounded-md border px-3 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50"
                      onChange={(event) =>
                        setPurgeConfirmationName(event.target.value)
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <label
                      htmlFor={`${id}-purge-password`}
                      className="text-sm font-medium"
                    >
                      Administrator password
                    </label>
                    <input
                      id={`${id}-purge-password`}
                      type="password"
                      value={purgePassword}
                      autoComplete="current-password"
                      disabled={busy}
                      className="border-input bg-card text-foreground focus-visible:outline-ring min-h-11 w-full rounded-md border px-3 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50"
                      onChange={(event) => setPurgePassword(event.target.value)}
                    />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="submit"
                      variant="destructive"
                      className="min-h-11"
                      disabled={
                        busy ||
                        purgeConfirmationName !==
                          purgePreview.confirmation_name ||
                        purgePassword.length === 0
                      }
                    >
                      {pending === "purge"
                        ? "Deleting…"
                        : "Delete record forever"}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      className="min-h-11"
                      disabled={busy}
                      onClick={() => {
                        clearPurgeReview();
                        setError("");
                      }}
                    >
                      Cancel
                    </Button>
                  </div>
                </form>
              )}
            </div>
          ) : null}
          {inPlace ? inPlace.renderDetails(inPlaceValue) : children}
        </>
      )}
      <AlertDialog
        open={confirmDelete}
        onOpenChange={(open) => {
          if (!busy) setConfirmDelete(open);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this record?</AlertDialogTitle>
            <AlertDialogDescription>
              It moves to deleted records, and its links are hidden. You can
              restore it later with its values and links.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <Button
              type="button"
              variant="outline"
              className="min-h-11"
              disabled={busy}
              onClick={() => setConfirmDelete(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              className="min-h-11"
              disabled={busy}
              onClick={() => void remove()}
            >
              {pending === "delete" ? "Deleting…" : "Delete record"}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
