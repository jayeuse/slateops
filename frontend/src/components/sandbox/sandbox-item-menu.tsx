"use client";

import { Pencil, Trash2 } from "lucide-react";

import {
  ContextMenuGroup,
  ContextMenuItem,
  ContextMenuSeparator,
} from "@/components/ui/context-menu";
import {
  itemMenuEntries,
  type ItemMenuAction,
  type ItemMenuKind,
} from "@/components/systems/sandbox/helpers/element-bar";

export type SandboxItemMenuProps = {
  kind: ItemMenuKind;
  closed: boolean;
  canPurge: boolean;
  /** A save holds the draft: the items wait. */
  pending: boolean;
  /** Live state is loading, or edits must be saved first. */
  lifecycleDisabled: boolean;
  /** Fewer than two modules: nothing to connect to. */
  connectDisabled?: boolean;
  onRename: () => void;
  onDelete: () => void;
  onToggleLifecycle?: () => void;
  onPurge?: () => void;
  onDuplicate?: () => void;
  onConnect?: () => void;
  onNewTrigger?: () => void;
};

/**
 * The item menu of a department, module, or field: the same items in the
 * Structure tree and on the canvas (FIND-6). It renders inside a
 * `ContextMenuContent` that its caller owns.
 */
export function SandboxItemMenuItems({
  kind,
  closed,
  canPurge,
  pending,
  lifecycleDisabled,
  connectDisabled = false,
  onRename,
  onDelete,
  onToggleLifecycle,
  onPurge,
  onDuplicate,
  onConnect,
  onNewTrigger,
}: SandboxItemMenuProps) {
  const entries = itemMenuEntries(kind, {
    closed,
    canPurge: canPurge && onPurge !== undefined,
    lifecycle: onToggleLifecycle !== undefined,
    duplicate: onDuplicate !== undefined,
    connect: onConnect !== undefined,
    newTrigger: onNewTrigger !== undefined,
  });
  const handlers: Record<ItemMenuAction, (() => void) | undefined> = {
    rename: onRename,
    lifecycle: onToggleLifecycle,
    purge: onPurge,
    duplicate: onDuplicate,
    connect: onConnect,
    newTrigger: onNewTrigger,
    delete: onDelete,
  };
  const disabled: Record<ItemMenuAction, boolean> = {
    rename: pending,
    lifecycle: pending || lifecycleDisabled,
    purge: pending || lifecycleDisabled,
    duplicate: pending,
    connect: connectDisabled,
    // The move to Triggers waits for the same work as the other items.
    newTrigger: pending,
    delete: pending,
  };
  const item = (entry: (typeof entries)[number]) => (
    <ContextMenuItem
      key={entry.action}
      className="min-h-11 min-w-11 xl:min-h-0 xl:min-w-0"
      variant={
        entry.action === "purge" || entry.action === "delete"
          ? "destructive"
          : undefined
      }
      disabled={disabled[entry.action]}
      onClick={handlers[entry.action]}
    >
      {entry.action === "rename" ? <Pencil aria-hidden="true" /> : null}
      {entry.action === "delete" ? <Trash2 aria-hidden="true" /> : null}
      {entry.label}
    </ContextMenuItem>
  );
  return (
    <>
      <ContextMenuGroup>
        {entries.filter((entry) => !entry.destructive).map(item)}
      </ContextMenuGroup>
      <ContextMenuSeparator />
      <ContextMenuGroup>
        {entries.filter((entry) => entry.destructive).map(item)}
      </ContextMenuGroup>
    </>
  );
}
