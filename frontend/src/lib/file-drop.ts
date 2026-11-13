import {
  useEffect,
  useRef,
  useState,
  type ClipboardEvent as ReactClipboardEvent,
  type DragEvent as ReactDragEvent,
} from "react";
import { MAX_FILE_BYTES } from "@/components/systems/shared/adapters/files-api";

// A dropped or pasted file attaches as "Choose file" does (candidate 7 of
// docs/specs/subtle-interactions.md, DR-SI-7.1 to DR-SI-7.4). The panels that
// offer "Choose file" (the record Files tab and the Files library) use these
// checks and hooks; no file of the app shell imports this module.

/**
 * The file types that "Choose file" offers; a drop gets the same courtesy
 * check. The server's file allowlist stays the control.
 */
export const UPLOAD_ACCEPT = ".pdf,.png,.jpg,.jpeg,.docx,.xlsx,.pptx";
const ACCEPTED = new Set(UPLOAD_ACCEPT.split(","));

export const FILE_DROP_WORDS = {
  oneFile: "Drop one file at a time.",
  busy: "Wait for the current upload to finish.",
  busyOther: "Wait a moment, then drop the file again.",
  type: "Choose a PDF, PNG, JPEG, Word, Excel, or PowerPoint file.",
  size: "Choose a file larger than 0 bytes and no larger than 25 MB.",
} as const;

export type DroppedFile = { name: string; size: number };

/**
 * What the panel's one operation is doing: an upload, another operation (a
 * download, an archive, a status check or "Load more"), or nothing.
 */
export type RunningOperation = "upload" | "other" | null;

/**
 * The checks before a dropped or pasted file uploads (DR-SI-7.3): one file,
 * no operation running, a type of the picker, and the size limit. Returns
 * the file to upload, the message that says why nothing uploads, or null
 * when the drop or paste carried no file.
 */
export function checkDroppedFiles<Item extends DroppedFile>(
  files: readonly Item[],
  running: RunningOperation,
): { file: Item } | { message: string } | null {
  const [file] = files;
  if (!file) return null;
  if (files.length > 1) return { message: FILE_DROP_WORDS.oneFile };
  if (running === "upload") return { message: FILE_DROP_WORDS.busy };
  if (running) return { message: FILE_DROP_WORDS.busyOther };
  const dot = file.name.lastIndexOf(".");
  if (dot < 0 || !ACCEPTED.has(file.name.slice(dot).toLowerCase()))
    return { message: FILE_DROP_WORDS.type };
  if (file.size < 1 || file.size > MAX_FILE_BYTES)
    return { message: FILE_DROP_WORDS.size };
  return { file };
}

/**
 * The drop state of a panel: a dashed outline and one centered line over it.
 * `m-0` keeps a parent's `space-y` margin off the overlay.
 */
export const DROP_STATE_CLASS_NAME =
  "pointer-events-none absolute inset-0 z-10 m-0 flex items-center justify-center rounded-lg border-2 border-dashed border-ring bg-action-tint p-4 text-center text-sm font-medium text-action-text";

function carriesFiles(transfer: DataTransfer | null): boolean {
  return Array.from(transfer?.types ?? []).includes("Files");
}

const NOT_TEXT = new Set([
  "button",
  "checkbox",
  "color",
  "file",
  "image",
  "radio",
  "range",
  "reset",
  "submit",
]);

/** A paste here belongs to the field: it stays text (DR-SI-7.2). */
function takesText(target: EventTarget | null): boolean {
  if (target instanceof HTMLTextAreaElement) return true;
  if (target instanceof HTMLInputElement) return !NOT_TEXT.has(target.type);
  return target instanceof HTMLElement && target.isContentEditable;
}

/**
 * Stops a file dropped outside a drop target from opening in the browser
 * and leaving the page (DR-SI-7.4). A target that takes the file cancels the
 * event itself first; this listener then leaves it alone.
 */
export function usePageFileDropGuard(enabled = true): void {
  useEffect(() => {
    if (!enabled) return;
    const ignore = (event: DragEvent) => {
      if (event.defaultPrevented || !carriesFiles(event.dataTransfer)) return;
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = "none";
    };
    window.addEventListener("dragover", ignore);
    window.addEventListener("drop", ignore);
    return () => {
      window.removeEventListener("dragover", ignore);
      window.removeEventListener("drop", ignore);
    };
  }, [enabled]);
}

/**
 * Makes a panel take a dropped file, and a file pasted while focus is in it
 * and not in a text field (DR-SI-7.1, DR-SI-7.2). `over` is true while a file
 * is dragged over the panel. When `enabled` is false the panel takes nothing
 * and shows no drop state.
 */
export function useFileDropZone(
  enabled: boolean,
  receive: (files: File[]) => void,
) {
  const [over, setOver] = useState(false);
  // dragenter and dragleave also fire for each child the file crosses.
  const depth = useRef(0);
  if (!enabled && over) setOver(false);
  const reset = () => {
    depth.current = 0;
    setOver(false);
  };
  const zone = enabled
    ? {
        onDragEnter(event: ReactDragEvent<HTMLElement>) {
          if (!carriesFiles(event.dataTransfer)) return;
          event.preventDefault();
          depth.current += 1;
          setOver(true);
        },
        onDragOver(event: ReactDragEvent<HTMLElement>) {
          if (!carriesFiles(event.dataTransfer)) return;
          event.preventDefault();
          event.dataTransfer.dropEffect = "copy";
        },
        onDragLeave(event: ReactDragEvent<HTMLElement>) {
          if (!carriesFiles(event.dataTransfer)) return;
          depth.current = Math.max(0, depth.current - 1);
          if (depth.current === 0) setOver(false);
        },
        onDrop(event: ReactDragEvent<HTMLElement>) {
          if (!carriesFiles(event.dataTransfer)) return;
          event.preventDefault();
          reset();
          receive(Array.from(event.dataTransfer.files));
        },
        onPaste(event: ReactClipboardEvent<HTMLElement>) {
          if (takesText(event.target)) return;
          const files = Array.from(event.clipboardData.files);
          if (!files.length) return;
          event.preventDefault();
          receive(files);
        },
      }
    : {};
  return { over: enabled && over, zone };
}
