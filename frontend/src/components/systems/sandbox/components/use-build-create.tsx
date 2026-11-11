"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";

import type {
  SandboxCanvasApi,
  SandboxElementBars,
} from "@/components/sandbox/sandbox-canvas";
import type { SandboxState } from "@/lib/sandbox/model";
import type { CreateKind } from "../domain/create-checks";
import { uid, type Design, type DesignUpdate } from "../domain/model";
import {
  connectTargetGroups,
  relationshipNamesInUse,
} from "../domain/relationship-name";
import { canvasFieldId, projectedField } from "../helpers/bridge";
import { refusedSaveClosesCreate } from "../helpers/create-hold";
import { elementBarOwner, savingMarkIds } from "../helpers/element-bar";
import {
  SandboxCommandError,
  type SandboxCommandResult,
} from "../state/commands";
import { addedElementIds } from "../state/save-queue";
import { ConnectPopover } from "./connect-popover";
import { CreateEntry } from "./create-entry";
import { ElementBarControls, type ElementBarOpen } from "./element-bar";

/** A new relationship's cardinality; it changes in the relationship's settings. */
export const DEFAULT_CARDINALITY = "One-to-many";

/**
 * Build's create surface (docs/specs/sandbox-ux-redesign.md, "Build: find
 * and create"): the element bars, the add-next entry, and Connect, with the
 * saving marks of new elements. The designer owns the selection and the
 * canvas; this hook owns the open entry or Connect, and which bar stays while
 * focus is in it or returns to it.
 */
export function useBuildCreate({
  design,
  projected,
  change,
  addHoldReason,
  saving,
  savingIds,
  canvasShown,
  graphRef,
  canvasFrameRef,
  setSelected,
  showProperties,
}: {
  design: Design;
  /** The canvas's projection of the design, with canvas field ids. */
  projected: SandboxState;
  change: (
    update: DesignUpdate,
    commandKey?: string,
  ) => Promise<SandboxCommandResult<Design>>;
  addHoldReason: string | null;
  /** The save queue holds the draft (`saveQueueActive`). */
  saving: boolean;
  savingIds: readonly string[];
  /** The canvas is on screen, so a new element can be brought into view. */
  canvasShown: boolean;
  graphRef: RefObject<SandboxCanvasApi | null>;
  canvasFrameRef: RefObject<HTMLDivElement | null>;
  setSelected: (id: string) => void;
  /** Shows Properties in the workbench, as a canvas selection does. */
  showProperties: () => void;
}) {
  // Create where the element grows (FIND-1 to FIND-6): the entry for a
  // department, module, or field, and Connect for a relationship. Each is
  // anchored to the control that opened it; `owner` is the element whose bar
  // holds that control, so the bar stays while the popover is open.
  const [entry, setEntry] = useState<{
    kind: CreateKind;
    parentId: string | null;
    anchor: HTMLElement;
    owner: string | null;
    /** Opened by the canvas toolbar's Add department. */
    toolbar: boolean;
  } | null>(null);
  const [connect, setConnect] = useState<{
    sourceId: string;
    anchor: HTMLElement;
    owner: string | null;
    /** The target of a line drawn between ports: chosen at open. */
    targetId: string | null;
  } | null>(null);
  const [connectPreview, setConnectPreview] = useState<string | null>(null);
  // A bar stays while focus is in it, and while focus returns to it after
  // its popover closes and the selection moves to the new element.
  const [barFocus, setBarFocus] = useState<string | null>(null);
  const [closingOwner, setClosingOwner] = useState<string | null>(null);
  // The element whose bar a focused Structure row shows; moving between rows
  // of one module changes nothing.
  const [focusedOwner, setFocusedOwner] = useState<string | null>(null);
  function setFocusedItem(id: string | null): void {
    setFocusedOwner(elementBarOwner(projected, id));
  }
  // A press on the anchor of an open popover closes it as an outside press;
  // the click that follows must not open it again.
  const lastClose = useRef<HTMLElement | null>(null);
  function justClosed(anchor: HTMLElement): boolean {
    return lastClose.current === anchor;
  }
  // Frame callbacks and the reopen guard end with Build.
  const frames = useRef(new Set<number>());
  const reopenTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  function afterFrame(callback: () => void): void {
    const id = requestAnimationFrame(() => {
      frames.current.delete(id);
      callback();
    });
    frames.current.add(id);
  }
  useEffect(() => {
    const pending = frames.current;
    return () => {
      for (const id of pending) cancelAnimationFrame(id);
      pending.clear();
      if (reopenTimer.current !== null) clearTimeout(reopenTimer.current);
    };
  }, []);
  function settleFocus(anchor: HTMLElement, owner: string | null): void {
    lastClose.current = anchor;
    if (reopenTimer.current !== null) clearTimeout(reopenTimer.current);
    reopenTimer.current = setTimeout(() => {
      reopenTimer.current = null;
      if (lastClose.current === anchor) lastClose.current = null;
    }, 400);
    setClosingOwner(owner);
    // Focus goes back to the anchor; if the selection change re-rendered it,
    // it is moved back once the selection settles.
    afterFrame(() => {
      const active = document.activeElement;
      if (anchor.isConnected && (active === null || active === document.body))
        anchor.focus();
      afterFrame(() =>
        setClosingOwner((current) => (current === owner ? null : current)),
      );
    });
  }
  function openEntry(
    kind: CreateKind,
    parentId: string | null,
    anchor: HTMLElement | null,
    owner: string | null,
    toolbar = false,
  ): void {
    if (anchor === null || justClosed(anchor)) return;
    setConnect(null);
    setEntry({ kind, parentId, anchor, owner, toolbar });
  }
  function closeEntry(lastCreatedId: string | null): void {
    const current = entry;
    if (current === null) return;
    setEntry(null);
    // The last element this flow created becomes the selection.
    if (lastCreatedId)
      setSelected(
        current.kind === "field" && current.parentId
          ? canvasFieldId(current.parentId, lastCreatedId)
          : lastCreatedId,
      );
    settleFocus(current.anchor, current.owner);
  }
  function openConnect(
    sourceId: string,
    anchor: HTMLElement | null,
    owner: string | null,
    targetId: string | null = null,
  ): void {
    if (anchor === null || justClosed(anchor)) return;
    setEntry(null);
    setConnect({ sourceId, anchor, owner, targetId });
  }
  function closeConnect(): void {
    const current = connect;
    if (current === null) return;
    setConnect(null);
    setConnectPreview(null);
    settleFocus(current.anchor, current.owner);
  }
  /** The Connect button on a module's bar, once the bar shows. */
  function barControl(owner: string, action: string): HTMLElement | null {
    const pinned = !window.matchMedia("(min-width: 48rem)").matches;
    return document.querySelector<HTMLElement>(
      `[data-element-bar="${CSS.escape(owner)}"]${pinned ? "[data-pinned]" : ":not([data-pinned])"} [data-bar-action="${action}"]`,
    );
  }
  /**
   * Connect from the canvas (a port drag or the item menu): the module is
   * selected, so its bar shows, and Connect opens from the bar's button. A
   * port drag also gives the target, which opens chosen.
   */
  function connectFromCanvas(sourceId: string, targetId?: string): void {
    setSelected(sourceId);
    showProperties();
    afterFrame(() =>
      afterFrame(() => {
        const anchor = barControl(sourceId, "connect");
        openConnect(
          sourceId,
          anchor ?? canvasFrameRef.current,
          anchor ? sourceId : null,
          targetId ?? null,
        );
      }),
    );
  }
  // A refused save (409 or a failure) closes an open entry or Connect, and
  // the page shows its alert (N1 rule 3). Any other hold keeps them open
  // with their controls disabled and the reason (rule 6).
  const previousHold = useRef({ hold: addHoldReason, saving });
  useEffect(() => {
    const next = { hold: addHoldReason, saving };
    if (refusedSaveClosesCreate(previousHold.current, next)) {
      if (entry) closeEntry(null);
      if (connect) closeConnect();
    }
    previousHold.current = next;
  }, [addHoldReason, saving]);
  // The newest element keeps the flow tint until the next add (FAST-6).
  const [newest, setNewest] = useState<string | null>(null);
  async function addFromEntry(
    update: (design: Design) => Design,
  ): Promise<SandboxCommandResult<Design>> {
    const added = { ids: [] as string[] };
    const result = await change((current) => {
      const next = update(current);
      added.ids = addedElementIds(current, next);
      return next;
    });
    if (result.ok)
      setNewest([...savingMarkIds(result.value, added.ids)][0] ?? null);
    return result;
  }
  // A new element out of view comes into view at once; no animated pan.
  // Added while the canvas was hidden (a phone's Structure pane), it comes
  // into view when the canvas shows.
  const revealed = useRef<string | null>(null);
  useEffect(() => {
    if (!newest || !canvasShown || revealed.current === newest) return;
    const nodeId = projectedField(design, newest)?.moduleId ?? newest;
    const frame = requestAnimationFrame(() => {
      revealed.current = newest;
      graphRef.current?.reveal(nodeId);
    });
    return () => cancelAnimationFrame(frame);
  }, [newest, canvasShown]);
  // The saving mark: queued adds the design still has (an Undo can leave an
  // id in the queue). Keyed by the ids, so the outline re-renders only when
  // the marks change.
  const savingKey = savingIds.join("\u0000");
  const savingMarks = useMemo(
    () => savingMarkIds(design, savingIds),
    [design, savingKey],
  );
  const newestShown =
    newest !== null &&
    (projectedField(design, newest) !== undefined ||
      design.modules.some((item) => item.id === newest) ||
      design.departments.some((item) => item.id === newest))
      ? newest
      : null;
  const canvasMarks = useMemo(
    () => ({
      saving: savingMarks,
      newest: newestShown,
      connectTarget: connectPreview,
    }),
    [savingMarks, newestShown, connectPreview],
  );
  // A closing popover keeps what it showed until its exit ends, so its title
  // does not change and it returns focus to its own anchor.
  const [shownEntry, setShownEntry] = useState(entry);
  if (entry !== null && entry !== shownEntry) setShownEntry(entry);
  const [shownConnect, setShownConnect] = useState(connect);
  if (connect !== null && connect !== shownConnect) setShownConnect(connect);
  const connectSource = shownConnect
    ? design.modules.find((item) => item.id === shownConnect.sourceId)
    : undefined;
  const entryDepartment =
    shownEntry?.kind === "module"
      ? design.departments.find((item) => item.id === shownEntry.parentId)
      : undefined;
  const entryModule =
    shownEntry?.kind === "field"
      ? design.modules.find((item) => item.id === shownEntry.parentId)
      : undefined;
  const elementBars: SandboxElementBars = {
    held: entry?.owner ?? connect?.owner ?? closingOwner ?? barFocus,
    focused: focusedOwner,
    label: (owner) =>
      `${
        (
          design.departments.find((item) => item.id === owner) ??
          design.modules.find((item) => item.id === owner)
        )?.name ?? ""
      } actions`,
    onFocusChange: (owner, focused) =>
      setBarFocus((current) =>
        focused ? owner : current === owner ? null : current,
      ),
    render: (owner, pinned) => {
      const departmentItem = design.departments.find(
        (item) => item.id === owner,
      );
      const moduleItem = design.modules.find((item) => item.id === owner);
      const item = departmentItem ?? moduleItem;
      if (!item) return null;
      const departmentIndex = design.departments.findIndex(
        (entry) => entry.id === (moduleItem?.department ?? owner),
      );
      const opened: ElementBarOpen =
        entry?.owner === owner
          ? entry.kind === "module"
            ? "module"
            : "field"
          : connect?.owner === owner
            ? "connect"
            : null;
      return (
        <ElementBarControls
          kind={departmentItem ? "department" : "module"}
          name={item.name}
          departmentIndex={Math.max(0, departmentIndex)}
          pinned={pinned}
          open={opened}
          connectReason={
            design.modules.length < 2 ? "Add a second module first." : null
          }
          onAddModule={(anchor) => openEntry("module", owner, anchor, owner)}
          onAddField={(anchor) => openEntry("field", owner, anchor, owner)}
          onConnect={(anchor) => openConnect(owner, anchor, owner)}
        />
      );
    },
  };
  async function connectModules({
    targetId,
    name: relationshipName,
  }: {
    targetId: string;
    name: string;
  }): Promise<SandboxCommandResult<Design>> {
    const sourceId = connect?.sourceId;
    if (!sourceId)
      return { ok: false, error: "Choose the module to connect from." };
    // Today's default cardinality; cardinality and linked fields stay in the
    // relationship's settings.
    return change((previous) => {
      if (
        !previous.modules.some((item) => item.id === sourceId) ||
        !previous.modules.some((item) => item.id === targetId)
      )
        throw new SandboxCommandError(
          "Choose existing source and target modules.",
        );
      if (
        previous.relationships.some(
          (item) => item.source === sourceId && item.target === targetId,
        )
      )
        throw new SandboxCommandError(
          "A relationship between these modules already exists.",
        );
      return {
        ...previous,
        relationships: [
          ...previous.relationships,
          {
            id: uid(),
            name: relationshipName,
            source: sourceId,
            target: targetId,
            cardinality: DEFAULT_CARDINALITY,
            fieldMappings: [],
          },
        ],
      };
    });
  }
  const popovers: ReactNode = (
    <>
      <CreateEntry
        kind={shownEntry?.kind ?? "department"}
        parent={
          entryDepartment
            ? {
                id: entryDepartment.id,
                name: entryDepartment.name,
                departmentId: entryDepartment.id,
              }
            : entryModule
              ? {
                  id: entryModule.id,
                  name: entryModule.name,
                  departmentId: entryModule.department,
                }
              : null
        }
        design={design}
        open={entry !== null}
        anchor={shownEntry?.anchor ?? null}
        onRequestClose={closeEntry}
        onAdd={addFromEntry}
        holdReason={addHoldReason}
      />
      {connectSource ? (
        <ConnectPopover
          source={{
            id: connectSource.id,
            name: connectSource.name,
            departmentId: connectSource.department,
          }}
          targets={connectTargetGroups(design, connectSource.id)}
          existingNames={relationshipNamesInUse(design, connectSource.id)}
          open={connect !== null}
          anchor={shownConnect?.anchor ?? null}
          onRequestClose={closeConnect}
          onConnect={connectModules}
          holdReason={addHoldReason}
          onTargetPreview={setConnectPreview}
          initialTargetId={shownConnect?.targetId ?? null}
        />
      ) : null}
    </>
  );
  return {
    /** The toolbar's Add department opened the open entry. */
    toolbarEntryOpen: entry?.toolbar === true,
    openEntry,
    openConnect,
    connectFromCanvas,
    setFocusedItem,
    elementBars,
    canvasMarks,
    savingMarks,
    newestShown,
    popovers,
  };
}
