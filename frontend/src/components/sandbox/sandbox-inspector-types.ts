import type {
  SandboxState,
  UpdateSandboxFieldPatch,
} from "@/lib/sandbox/model";
import type { SandboxCommandResult } from "@/components/systems/sandbox/state/commands";
import type { SandboxDesignTarget } from "@/components/systems/sandbox/domain/model";

type SandboxCommand =
  | void
  | SandboxCommandResult<unknown>
  | PromiseLike<SandboxCommandResult<unknown> | void>;

export type SandboxInspectorTargetKind = SandboxDesignTarget["kind"];
export type SandboxInspectorTarget = SandboxDesignTarget;

export interface SandboxInspectorProps {
  state: SandboxState;
  onRenameDepartment: (departmentId: string, name: string) => SandboxCommand;
  onRenameModule: (moduleId: string, name: string) => SandboxCommand;
  onUpdateField: (
    fieldId: string,
    patch: UpdateSandboxFieldPatch,
  ) => SandboxCommand;
  onDeleteSelected: (target: SandboxInspectorTarget) => void;
  /** The add item opens the entry anchored to its row (FIND-4). */
  onAddField: (moduleId: string, anchor: HTMLElement) => void;
  onAddModule: (departmentId: string, anchor: HTMLElement) => void;
  onAddDepartment: (anchor: HTMLElement) => void;
  onSelect: (cellId: string) => void;
  onEdit?: (cellId: string) => void;
  onAddRelationship?: (anchor: HTMLElement) => void;
  /** "Connect…" in a module's item menu; `anchor` is the module's row. */
  onConnect?: (moduleId: string, anchor: HTMLElement) => void;
  /** "New trigger" in a module's item menu (TRIG-8); absent until wired. */
  onNewTrigger?: (moduleId: string) => void;
  /** A tree item took or lost focus: its element's bar shows on the canvas. */
  onFocusItem?: (cellId: string | null) => void;
  /** Rows whose add is still saving (the saving mark). */
  savingIds?: ReadonlySet<string>;
  /** The newest added row, tinted until the next add. */
  newestId?: string | null;
  onDuplicate?: (target: SandboxInspectorTarget) => void;
  onToggleLifecycle?: (target: SandboxInspectorTarget) => void;
  lifecycleState?: (target: SandboxInspectorTarget) => {
    closed: boolean;
    canPurge: boolean;
    disabled: boolean;
  };
  onPurge?: (target: SandboxInspectorTarget) => SandboxCommand;
  onEditingChange?: (editing: boolean) => void;
  pending?: boolean;
}
