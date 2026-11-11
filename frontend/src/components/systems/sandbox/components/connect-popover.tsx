"use client";

import { Check } from "lucide-react";
import {
  useEffect,
  useId,
  useRef,
  useState,
  useSyncExternalStore,
  type ComponentType,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
} from "react";
import { flushSync } from "react-dom";

import { DepartmentMark } from "@/components/sandbox/department-mark";
import { Button } from "@/components/ui/button";
import { DisabledReason } from "@/components/ui/disabled-reason";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTitle } from "@/components/ui/popover";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

import {
  chooseTarget,
  connectSubmission,
  draftName,
  EMPTY_CONNECT_DRAFT,
  nameProblem,
  nextChoosable,
  typeAheadMatch,
  typeName,
  type ConnectDraft,
  type ConnectRequest,
  type ConnectTargetGroup,
  type RelationshipNamesInUse,
} from "../domain/relationship-name";
import type { SandboxCommandResult } from "../state/commands";
import { PropertyRow } from "./designer-properties";

export type ConnectSource = { id: string; name: string; departmentId: string };

export type ConnectPopoverProps = {
  /** The module whose bar or menu opened the popover. */
  source: ConnectSource;
  /** From `connectTargetGroups(design, source.id)`. */
  targets: readonly ConnectTargetGroup[];
  /** From `relationshipNamesInUse(design, source.id)`. */
  existingNames: RelationshipNamesInUse;
  open: boolean;
  /** The control that opened the popover; focus returns to it on close. */
  anchor: HTMLElement | null;
  onRequestClose: () => void;
  /**
   * Builds the relationship with today's default cardinality through
   * `change` and returns its immediate result; a refusal shows in place.
   */
  onConnect: (
    request: ConnectRequest,
  ) => Promise<SandboxCommandResult<unknown>>;
  /** Rule 6: a publish, lifecycle action or conflict holds the draft. */
  holdReason: string | null;
  /** The chosen target, for the dashed edge on the canvas; null on close. */
  onTargetPreview: (targetId: string | null) => void;
};

const PHONE_QUERY = "(max-width: 767px)";
const TYPE_AHEAD_MS = 700;

function subscribePhone(onChange: () => void): () => void {
  const query = window.matchMedia(PHONE_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/** Phones get a bottom sheet with 44px controls (B10). */
function usePhone(): boolean {
  return useSyncExternalStore(
    subscribePhone,
    () => window.matchMedia(PHONE_QUERY).matches,
    () => false,
  );
}

/**
 * Connect from a module (FAST-4): choose a target, then the Name, prefilled
 * and checked against the source's names (N6). Anchored to the control that
 * opened it; a bottom sheet on phones. Escape closes and returns focus to
 * the anchor.
 */
export function ConnectPopover({
  open,
  anchor,
  onRequestClose,
  onTargetPreview,
  ...rest
}: ConnectPopoverProps) {
  const phone = usePhone();
  const listRef = useRef<HTMLDivElement>(null);
  function close(): void {
    onTargetPreview(null);
    onRequestClose();
  }
  const finalFocus = () => anchor ?? true;
  const body = (Title: TitleComponent) => (
    <ConnectPopoverBody
      {...rest}
      onRequestClose={close}
      onTargetPreview={onTargetPreview}
      listRef={listRef}
      Title={Title}
      phone={phone}
    />
  );
  if (phone)
    return (
      <Sheet open={open} onOpenChange={(next) => (next ? undefined : close())}>
        <SheetContent
          initialFocus={listRef}
          finalFocus={finalFocus}
          className="inset-x-0 top-auto bottom-0 max-h-[min(80dvh,40rem)] w-full gap-0 rounded-t-xl border-t border-l-0 p-0 pb-[env(safe-area-inset-bottom)] data-ending-style:translate-x-0 data-ending-style:translate-y-full data-starting-style:translate-x-0 data-starting-style:translate-y-full"
        >
          {body(SheetTitle)}
        </SheetContent>
      </Sheet>
    );
  return (
    <Popover open={open} onOpenChange={(next) => (next ? undefined : close())}>
      <PopoverContent
        anchor={anchor}
        align="start"
        side="bottom"
        sideOffset={6}
        collisionPadding={16}
        initialFocus={listRef}
        finalFocus={finalFocus}
        className="slim-ui w-96 max-w-[calc(100vw-2rem)] gap-0 p-0"
      >
        {body(PopoverTitle)}
      </PopoverContent>
    </Popover>
  );
}

type TitleComponent = ComponentType<{
  className?: string;
  children: ReactNode;
}>;

/** The popover's content; exported for markup tests. */
export function ConnectPopoverBody({
  source,
  targets,
  existingNames,
  holdReason,
  onRequestClose,
  onConnect,
  onTargetPreview,
  listRef,
  Title,
  phone,
}: Omit<ConnectPopoverProps, "open" | "anchor"> & {
  listRef: RefObject<HTMLDivElement | null>;
  Title: TitleComponent;
  phone: boolean;
}) {
  const id = useId();
  const typeAhead = useRef({ text: "", at: 0 });
  const [draft, setDraft] = useState<ConnectDraft>(EMPTY_CONNECT_DRAFT);
  const [activeId, setActiveId] = useState(() =>
    nextChoosable(targets, null, 1),
  );
  const [refusal, setRefusal] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const name = draftName(draft, source.name, targets, existingNames);
  const problem =
    refusal ??
    (name.trim() ? nameProblem(name, existingNames, source.name) : null);
  const connectReason =
    holdReason ?? (draft.targetId ? null : "Choose a module to connect to.");
  const sourceIndex =
    targets.find((group) => group.departmentId === source.departmentId)
      ?.departmentIndex ?? 0;
  const optionId = (moduleId: string) => `${id}-option-${moduleId}`;
  const nameId = `${id}-name`;
  const problemId = `${id}-problem`;

  // Keep the active row in view as arrows and type-ahead move it.
  useEffect(() => {
    if (activeId)
      document
        .getElementById(`${id}-option-${activeId}`)
        ?.scrollIntoView({ block: "nearest" });
  }, [id, activeId]);

  function choose(targetId: string): void {
    const next = chooseTarget(draft, targets, targetId);
    if (next === draft) return;
    // Render the prefilled name first, so focus lands after its last letter.
    flushSync(() => {
      setDraft(next);
      setActiveId(targetId);
      setRefusal(null);
    });
    onTargetPreview(targetId);
    const input = document.getElementById(nameId);
    if (!(input instanceof HTMLInputElement)) return;
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  }

  function onListKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    const step =
      event.key === "ArrowDown" ? 1 : event.key === "ArrowUp" ? -1 : null;
    if (step) {
      event.preventDefault();
      setActiveId(nextChoosable(targets, activeId, step));
      return;
    }
    if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      const ids = targets
        .flatMap((group) => group.modules)
        .filter((item) => item.state === "choosable")
        .map((item) => item.id);
      setActiveId((event.key === "Home" ? ids[0] : ids.at(-1)) ?? null);
      return;
    }
    // A space typed mid-word ("Field s…") searches; on its own it chooses.
    const typing = Date.now() - typeAhead.current.at <= TYPE_AHEAD_MS;
    if (event.key === "Enter" || (event.key === " " && !typing)) {
      event.preventDefault();
      if (activeId) choose(activeId);
      return;
    }
    if (
      event.key.length === 1 &&
      !event.ctrlKey &&
      !event.metaKey &&
      !event.altKey
    ) {
      event.preventDefault();
      const now = Date.now();
      const buffer = typeAhead.current;
      buffer.text =
        now - buffer.at > TYPE_AHEAD_MS ? event.key : buffer.text + event.key;
      buffer.at = now;
      const match = typeAheadMatch(targets, buffer.text, activeId);
      if (match) setActiveId(match);
    }
  }

  // Enter in Name connects here too: a Connect that says why it waits
  // ignores its click, which would swallow the form's own Enter.
  async function connect(): Promise<void> {
    if (pending) return;
    if (holdReason) {
      setRefusal(holdReason);
      return;
    }
    const submission = connectSubmission(
      draft,
      source.name,
      targets,
      existingNames,
    );
    if (!submission.ok) {
      setRefusal(submission.reason);
      return;
    }
    setPending(true);
    const result = await onConnect(submission.request);
    setPending(false);
    if (result.ok) onRequestClose();
    else setRefusal(result.error);
  }

  const flat = targets.length < 2;
  const option = (item: ConnectTargetGroup["modules"][number]) => {
    const choosable = item.state === "choosable";
    const chosen = item.id === draft.targetId;
    return (
      <div
        key={item.id}
        role="option"
        id={optionId(item.id)}
        aria-selected={chosen}
        aria-disabled={choosable ? undefined : true}
        data-active={item.id === activeId ? "" : undefined}
        className={cn(
          "flex min-h-11 items-center gap-2 pr-2.5 text-sm",
          flat ? "pl-2.5" : "pl-6.5",
          choosable
            ? "cursor-pointer hover:bg-(--surface-hover) data-active:bg-(--surface-hover)"
            : "text-muted-foreground cursor-default",
          chosen && "bg-muted data-active:bg-muted font-medium",
        )}
        onClick={() => choose(item.id)}
      >
        {item.name}
        {item.state === "self" ? (
          <span className="text-muted-foreground ml-auto text-xs">
            this module
          </span>
        ) : item.state === "linked" ? (
          <span className="text-muted-foreground ml-auto text-xs">
            already linked
          </span>
        ) : chosen ? (
          <Check
            aria-hidden="true"
            className="text-muted-foreground ml-auto size-3.5"
          />
        ) : null}
      </div>
    );
  };

  return (
    <form
      className="flex min-h-0 flex-col"
      noValidate
      onSubmit={(event: FormEvent) => {
        event.preventDefault();
        void connect();
      }}
    >
      <Title className="flex items-center gap-2 px-3.5 pt-3 text-sm font-semibold">
        <DepartmentMark departmentIndex={sourceIndex} />
        Connect {source.name} to
      </Title>
      <div className="grid min-h-0 gap-2.5 px-3.5 pt-2.5 pb-3">
        <div
          ref={listRef}
          role="listbox"
          aria-label="Target module"
          tabIndex={0}
          aria-activedescendant={activeId ? optionId(activeId) : undefined}
          onKeyDown={onListKeyDown}
          className="ring-border focus-visible:outline-ring max-h-64 overflow-y-auto rounded-md py-0.5 ring-1 ring-inset focus-visible:outline-2 focus-visible:outline-offset-1"
        >
          {flat
            ? targets.flatMap((group) => group.modules.map(option))
            : targets.map((group) => (
                <div
                  key={group.departmentId}
                  role="group"
                  aria-label={group.departmentName}
                >
                  <div
                    aria-hidden="true"
                    className="text-muted-foreground flex h-7 items-center gap-2 px-2.5 text-xs font-semibold"
                  >
                    <DepartmentMark departmentIndex={group.departmentIndex} />
                    {group.departmentName}
                  </div>
                  {group.modules.map(option)}
                </div>
              ))}
        </div>
        <PropertyRow
          id={nameId}
          label="Name"
          error={problem ?? undefined}
          errorId={problemId}
        >
          <Input
            id={nameId}
            className="h-11"
            value={name}
            autoComplete="off"
            aria-invalid={problem ? true : undefined}
            aria-describedby={problem ? problemId : undefined}
            onChange={(event) => {
              setDraft(typeName(draft, event.target.value));
              setRefusal(null);
            }}
            onKeyDown={(event) => {
              if (event.key !== "Enter" || event.nativeEvent.isComposing)
                return;
              event.preventDefault();
              void connect();
            }}
          />
        </PropertyRow>
      </div>
      <div
        className={cn(
          "border-border flex items-center justify-end gap-1.5 border-t px-3.5 py-2.5",
          phone && "pb-4 [&>*]:flex-1",
        )}
      >
        <Button
          type="button"
          variant="ghost"
          className="h-11"
          onClick={onRequestClose}
        >
          Cancel
        </Button>
        <DisabledReason stable reason={connectReason}>
          <Button type="submit" className="h-11" disabled={pending}>
            Connect
          </Button>
        </DisabledReason>
      </div>
    </form>
  );
}
