"use client";

import {
  createContext,
  memo,
  useContext,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type KeyboardEvent,
  type PointerEvent,
} from "react";
import {
  EdgeLabelRenderer,
  getSmoothStepPath,
  Handle,
  Position,
  type EdgeProps,
  type NodeProps,
} from "@xyflow/react";

import { FIELD_TYPE_META } from "@/lib/sandbox/model";
import {
  DEPARTMENT_HEAD_HEIGHT,
  MODULE_TABLE,
  moduleTableHeight,
  relationshipLineAttrs,
  truncateLabel,
} from "@/lib/sandbox/canvas-geometry";
import type {
  DepartmentFlowNode,
  ModuleFlowNode,
  RelationshipFlowEdge,
} from "./sandbox-flow-model";
import {
  fieldMarkDescription,
  useFieldMarks,
  useTraceMark,
  type SandboxCanvasTraceStore,
  type TraceMark,
} from "./sandbox-canvas-trace";
import {
  LINE_PATH,
  pathPoints,
  pointAlong,
  useLineLabelStop,
  type LineLabelStops,
} from "./sandbox-canvas-labels";

/**
 * Node and line views for the Sandbox canvas. Each draws the same SVG the
 * look stylesheets target (`data-sandbox-*` hooks, colors as presentation
 * attributes so the cascade can override them). Views are memoized and read
 * the canvas actions from one stable context.
 */

export interface CanvasEditRequest {
  target: "department" | "module" | "field";
  property: "name" | "type";
  id: string;
  nodeId: string;
  rowIndex?: number;
}

/** Marks the Build page draws on the canvas while it creates elements. */
export interface CanvasMarks {
  /** Canvas ids whose add is still saving (the saving mark). */
  saving: ReadonlySet<string>;
  /** The newest added canvas id, tinted until the next add. */
  newest: string | null;
  /** The module that Connect would link to: a dashed edge on its card. */
  connectTarget: string | null;
}

const NO_MARKS: CanvasMarks = {
  saving: new Set(),
  newest: null,
  connectTarget: null,
};

/** A small external store, so marks re-render the node views only. */
export class SandboxCanvasMarks {
  private value: CanvasMarks = NO_MARKS;
  private readonly listeners = new Set<() => void>();

  get = (): CanvasMarks => this.value;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  set(next: CanvasMarks): void {
    const current = this.value;
    if (
      current.newest === next.newest &&
      current.connectTarget === next.connectTarget &&
      current.saving.size === next.saving.size &&
      [...next.saving].every((id) => current.saving.has(id))
    )
      return;
    this.value = next;
    for (const listener of this.listeners) listener();
  }
}

function useCanvasMarks(store: SandboxCanvasMarks): CanvasMarks {
  return useSyncExternalStore(store.subscribe, store.get, store.get);
}

/** The saving mark: a small ring in muted ink at the end of a row. */
function SavingRing({ cx, cy }: { cx: number; cy: number }) {
  return (
    <g data-sandbox-part="saving-mark" aria-hidden="true" pointerEvents="none">
      <circle
        cx={cx}
        cy={cy}
        r={4.5}
        fill="none"
        stroke="var(--rule-strong)"
        strokeWidth={1.5}
      />
      <path
        d={`M${cx - 3.18} ${cy - 3.18}A4.5 4.5 0 0 1 ${cx + 3.18} ${cy - 3.18}`}
        fill="none"
        stroke="var(--ink-muted)"
        strokeWidth={1.5}
      />
    </g>
  );
}

export interface SandboxCanvasActions {
  trace: SandboxCanvasTraceStore;
  labels: LineLabelStops;
  marks: SandboxCanvasMarks;
  openEditor: (request: CanvasEditRequest) => void;
  startResize: (departmentId: string, event: PointerEvent<SVGElement>) => void;
  resizeByKey: (departmentId: string, event: KeyboardEvent<SVGElement>) => void;
}

const SandboxCanvasActionsContext = createContext<SandboxCanvasActions | null>(
  null,
);

export const SandboxCanvasActionsProvider =
  SandboxCanvasActionsContext.Provider;

function useCanvasActions(): SandboxCanvasActions {
  const actions = useContext(SandboxCanvasActionsContext);
  if (actions === null)
    throw new Error("Sandbox canvas nodes need SandboxCanvasActionsProvider.");
  return actions;
}

/** A pointer event in the node's own canvas units, at any zoom. */
export function nodePoint(
  element: Element,
  clientX: number,
  clientY: number,
  width: number,
): { x: number; y: number } {
  const box = element.getBoundingClientRect();
  const scale = box.width > 0 ? box.width / width : 1;
  return { x: (clientX - box.left) / scale, y: (clientY - box.top) / scale };
}

const CANVAS_NODE_ACTIVE = "var(--primary)";

function DepartmentNodeView({
  id,
  data,
  width = 0,
  height = 0,
}: NodeProps<DepartmentFlowNode>) {
  const actions = useCanvasActions();
  const marks = useCanvasMarks(actions.marks);
  const { name, moduleCount, tone, selected, feedback } = data;
  const saving = marks.saving.has(id);
  const moving = feedback === "moving";
  const dropTarget = feedback === "drop";
  const active = dropTarget || selected;
  return (
    <svg
      data-sandbox-node={id}
      width={width}
      height={height}
      overflow="visible"
      className="block"
      onDoubleClick={(event) => {
        const point = nodePoint(
          event.currentTarget,
          event.clientX,
          event.clientY,
          width,
        );
        if (point.y > 36) return;
        event.stopPropagation();
        actions.openEditor({
          target: "department",
          property: "name",
          id,
          nodeId: id,
        });
      }}
    >
      <rect
        // Theme skin hooks (src/app/themes).
        data-sandbox-body="true"
        data-sandbox-kind="department"
        data-selected={selected ? "true" : "false"}
        data-feedback={feedback ?? ""}
        width={width}
        height={height}
        // Corners come from the look's --radius in CSS (globals.css); these
        // are the Slate values for a missing stylesheet.
        rx={14}
        ry={14}
        fill={
          moving
            ? "var(--canvas-moving)"
            : dropTarget
              ? "var(--canvas-drop)"
              : selected
                ? "var(--accent)"
                : `var(--dept-${tone}-sheet)`
        }
        stroke={
          moving
            ? "var(--warning)"
            : active
              ? CANVAS_NODE_ACTIVE
              : "var(--canvas-dept-frame)"
        }
        strokeWidth={moving || active ? 2 : 1}
      />
      {/* The head band, top edge, and identity mark exist in every theme;
          each theme colors them through --dept-n-band and --dept-n. */}
      <rect
        data-sandbox-part="band"
        x={1}
        y={1}
        width={Math.max(width - 2, 0)}
        height={DEPARTMENT_HEAD_HEIGHT - 1}
        fill={`var(--dept-${tone}-band, transparent)`}
        pointerEvents="none"
      />
      {/* The department color as a 3px top edge that follows the frame's
          corners: the frame's shape, clipped to its top in CSS. A state
          stroke runs along the top too, so the edge takes its color. */}
      <rect
        data-sandbox-part="edge"
        width={width}
        height={height}
        rx={14}
        ry={14}
        fill={
          moving
            ? "var(--warning)"
            : active
              ? CANVAS_NODE_ACTIVE
              : `var(--dept-${tone})`
        }
        pointerEvents="none"
      />
      <rect
        data-sandbox-part="identity"
        x={16}
        y={16}
        width={10}
        height={10}
        rx={3}
        fill={`var(--dept-${tone})`}
        pointerEvents="none"
      />
      <text
        // Set in the look's display face (globals.css).
        data-sandbox-part="department-name"
        x={34}
        y={21}
        dominantBaseline="central"
        fontSize={15}
        fontWeight={700}
        fill={
          moving
            ? "var(--warning)"
            : active
              ? CANVAS_NODE_ACTIVE
              : saving
                ? "var(--ink-muted)"
                : "var(--canvas-dept-name)"
        }
        pointerEvents="none"
      >
        {truncateLabel(name, 30)}
      </text>
      {saving ? <SavingRing cx={width - 21} cy={21} /> : null}
      <text
        data-sandbox-part="module-count"
        x={width - (saving ? 34 : 16)}
        y={21}
        textAnchor="end"
        dominantBaseline="central"
        fontSize={12}
        fill="var(--canvas-dept-ink)"
        pointerEvents="none"
      >
        {`${moduleCount} ${moduleCount === 1 ? "module" : "modules"}`}
      </text>
      {selected ? (
        <>
          <rect
            className="nodrag nopan"
            data-department-resize="true"
            role="button"
            tabIndex={0}
            aria-label="Resize department"
            x={width - 24}
            y={height - 24}
            width={24}
            height={24}
            rx={4}
            fill="transparent"
            cursor="nwse-resize"
            style={{ touchAction: "none" }}
            onPointerDown={(event) => actions.startResize(id, event)}
            onKeyDown={(event) => actions.resizeByKey(id, event)}
            onDoubleClick={(event) => event.stopPropagation()}
          />
          <path
            d={`M${width - 17} ${height - 7}l10 -10 M${width - 11} ${height - 7}l4 -4`}
            stroke={CANVAS_NODE_ACTIVE}
            strokeWidth={2}
            fill="none"
            pointerEvents="none"
          />
        </>
      ) : null}
    </svg>
  );
}

/** The table glyph beside a module name (16px box, as on the website). */
function tableGlyphPath(x: number, y: number): string {
  return (
    `M${x + 4} ${y + 2.5}h8a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-8a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2Z` +
    `M${x + 2} ${y + 6.5}h12M${x + 6.5} ${y + 6.5}v7`
  );
}

const TYPE_INK = "var(--canvas-type-ink)";

function ModuleNodeView({ id, data }: NodeProps<ModuleFlowNode>) {
  const actions = useCanvasActions();
  const trace = useTraceMark(actions.trace, id);
  const marks = useFieldMarks(actions.trace);
  const created = useCanvasMarks(actions.marks);
  const { name, rows, tone, selected, selectedFieldId, feedback } = data;
  const moduleSaving = created.saving.has(id);
  // The chosen Connect target takes a dashed edge while Connect is open.
  const connectTarget = created.connectTarget === id;
  const { width, headerHeight, rowHeight, splitX } = MODULE_TABLE;
  const height = moduleTableHeight(rows.length);
  const rowCount = Math.max(rows.length, 1);
  const portsVisible = selected || selectedFieldId !== null;
  return (
    <>
      <svg
        data-sandbox-node={id}
        data-trace={trace ?? undefined}
        width={width}
        height={height}
        overflow="visible"
        className="block"
        onDoubleClick={(event) => {
          const point = nodePoint(
            event.currentTarget,
            event.clientX,
            event.clientY,
            width,
          );
          event.stopPropagation();
          if (point.y < headerHeight) {
            actions.openEditor({
              target: "module",
              property: "name",
              id,
              nodeId: id,
            });
            return;
          }
          const rowIndex = Math.floor((point.y - headerHeight) / rowHeight);
          const field = rows[rowIndex];
          if (field === undefined) return;
          actions.openEditor({
            target: "field",
            property: point.x >= splitX ? "type" : "name",
            id: field.id,
            nodeId: id,
            rowIndex,
          });
        }}
      >
        <rect
          // Theme skin hooks (src/app/themes).
          data-sandbox-body="true"
          data-sandbox-kind="module"
          data-selected={selected ? "true" : "false"}
          data-feedback={feedback ?? ""}
          width={width}
          height={height}
          // Corners come from the look's --radius in CSS (globals.css).
          rx={10}
          ry={10}
          fill={
            feedback === "moving"
              ? "var(--canvas-moving)"
              : selected
                ? "var(--accent)"
                : `var(--dept-${tone}-module)`
          }
          stroke={
            feedback === "moving"
              ? "var(--warning)"
              : selected
                ? CANVAS_NODE_ACTIVE
                : connectTarget
                  ? "var(--ink-muted)"
                  : "var(--canvas-module-frame)"
          }
          strokeWidth={feedback === null && !selected ? 1 : 2}
          strokeDasharray={connectTarget ? "4 3" : undefined}
          data-connect-target={connectTarget ? "true" : undefined}
        />
        <rect
          // The header follows the body's corner shape.
          data-sandbox-part="header"
          data-selected={selected ? "true" : "false"}
          width={width}
          height={headerHeight}
          rx={10}
          ry={10}
          fill={
            feedback === "moving"
              ? "var(--warning)"
              : selected
                ? "var(--accent)"
                : `var(--dept-${tone}-card)`
          }
        />
        <path
          data-sandbox-part="glyph"
          aria-hidden="true"
          d={tableGlyphPath(10, headerHeight / 2 - 8)}
          fill="none"
          stroke={TYPE_INK}
          strokeWidth={1.4}
          pointerEvents="none"
        />
        <text
          // The header bar under it takes the pointer, so the whole header
          // is one target.
          x={32}
          y={headerHeight / 2}
          dominantBaseline="central"
          fontSize={13}
          fontWeight={600}
          fill={moduleSaving ? "var(--ink-muted)" : "var(--canvas-module-ink)"}
          pointerEvents="none"
        >
          {truncateLabel(name, 24)}
        </text>
        {moduleSaving ? (
          <SavingRing cx={width - 16} cy={headerHeight / 2} />
        ) : null}
        {Array.from({ length: rowCount }, (_, index) => {
          const field = rows[index];
          const rowTop = headerHeight + index * rowHeight;
          const rowCenter = rowTop + rowHeight / 2;
          const last = index === rowCount - 1;
          const fieldSelected =
            field !== undefined && field.id === selectedFieldId;
          const mark =
            field === undefined ? undefined : marks?.[field.id] || undefined;
          const fieldSaving =
            field !== undefined && created.saving.has(field.id);
          const newest = field !== undefined && created.newest === field.id;
          return (
            <g key={field?.id ?? "empty"}>
              <rect
                x={1}
                y={rowTop}
                width={width - 2}
                height={rowHeight - (last ? 1 : 0)}
                rx={last ? 9 : 0}
                fill={
                  fieldSelected
                    ? "var(--accent)"
                    : newest
                      ? "color-mix(in oklab, var(--flow) 12%, transparent)"
                      : index % 2 === 1
                        ? `var(--dept-${tone}-stripe)`
                        : `var(--dept-${tone}-module)`
                }
                stroke={fieldSelected ? CANVAS_NODE_ACTIVE : "none"}
                strokeWidth={fieldSelected ? 1 : 0}
                tabIndex={field === undefined ? -1 : 0}
                role={field === undefined ? "presentation" : "button"}
                data-field-id={field?.id ?? ""}
                data-selected={fieldSelected ? "true" : "false"}
                data-feedback={fieldSelected ? "selected" : ""}
                data-test-mark={mark}
                data-saving={fieldSaving ? "true" : undefined}
                aria-busy={fieldSaving ? "true" : undefined}
                aria-description={
                  mark === undefined ? undefined : fieldMarkDescription(mark)
                }
                aria-pressed={
                  field === undefined
                    ? undefined
                    : fieldSelected
                      ? "true"
                      : "false"
                }
                aria-label={
                  field === undefined
                    ? "No fields yet"
                    : `${field.name}, ${FIELD_TYPE_META[field.type].label}, ${field.required ? "required" : "optional"}`
                }
              />
              <line
                x1={0}
                y1={rowTop}
                x2={width}
                y2={rowTop}
                stroke="var(--canvas-row-rule)"
                strokeWidth={1}
                pointerEvents="none"
              />
              {field === undefined ? null : (
                // Required fields have a filled marker, optional fields a
                // hollow one; the canvas key names both.
                <circle
                  aria-hidden="true"
                  cx={14}
                  cy={rowCenter}
                  r={3}
                  fill={field.required ? TYPE_INK : "none"}
                  stroke={TYPE_INK}
                  strokeWidth={1.25}
                  pointerEvents="none"
                />
              )}
              <text
                data-sandbox-part="field-name"
                x={26}
                y={rowCenter}
                dominantBaseline="central"
                fontSize={12}
                fill={
                  field === undefined
                    ? TYPE_INK
                    : fieldSaving
                      ? "var(--ink-muted)"
                      : "var(--canvas-field-ink)"
                }
                fontStyle={field === undefined ? "italic" : "normal"}
                pointerEvents="none"
              >
                {field === undefined
                  ? "No fields yet"
                  : // A longer type word ("Date and time") takes room from
                    // the name, so the two never touch in the 232 px card.
                    truncateLabel(
                      field.name,
                      Math.min(
                        18,
                        28 - FIELD_TYPE_META[field.type].label.length,
                      ),
                    )}
              </text>
              {field === undefined ? null : (
                <text
                  // Field types are data, set in the look's code face; the
                  // same words the Properties panel uses.
                  data-sandbox-part="field-type"
                  x={width - (fieldSaving ? 24 : 10)}
                  y={rowCenter}
                  textAnchor="end"
                  dominantBaseline="central"
                  fontSize={12}
                  fill={TYPE_INK}
                  pointerEvents="none"
                >
                  {FIELD_TYPE_META[field.type].label}
                </text>
              )}
              {fieldSaving ? (
                <SavingRing cx={width - 12} cy={rowCenter} />
              ) : null}
            </g>
          );
        })}
      </svg>
      {/* Connection points: hidden until the module is hovered or selected,
          or while a connection is being drawn (globals.css). */}
      <Handle
        type="target"
        position={Position.Left}
        id="in"
        className="sandbox-port"
        data-visible={portsVisible ? "true" : "false"}
      />
      <Handle
        type="source"
        position={Position.Right}
        id="out"
        className="sandbox-port"
        data-visible={portsVisible ? "true" : "false"}
      />
    </>
  );
}

/**
 * Line arrowheads, one per line color; ids are shared by every line. A traced
 * line turns the flow color (globals.css), and so does its arrowhead.
 */
export function RelationshipMarkers() {
  return (
    <svg aria-hidden="true" width={0} height={0} className="absolute">
      <defs>
        {(
          [
            ["relationship", relationshipLineAttrs(false, false).stroke],
            ["handoff", relationshipLineAttrs(false, true).stroke],
            ["selected", relationshipLineAttrs(true, false).stroke],
            ["trace", "var(--flow)"],
          ] as const
        ).map(([kind, color]) => (
          <marker
            key={kind}
            id={`sandbox-arrow-${kind}`}
            viewBox="0 0 8 7"
            refX={8}
            refY={3.5}
            markerWidth={8}
            markerHeight={7}
            markerUnits="userSpaceOnUse"
            orient="auto"
          >
            <path d="M0 0L8 3.5L0 7Z" fill={color} />
          </marker>
        ))}
      </defs>
    </svg>
  );
}

const LABEL_PADDING = { x: 7, y: 3 } as const;

/**
 * A line's name, drawn in React Flow's label layer above the tables (as X6
 * drew it), so a table over the line's middle never hides it. It fades with
 * its line during a hover trace.
 */
function LineLabel({
  id,
  x,
  y,
  text,
  handoff,
  trace,
}: {
  id: string;
  x: number;
  y: number;
  text: string;
  handoff: boolean;
  trace: TraceMark;
}) {
  const textRef = useRef<SVGTextElement | null>(null);
  // Approximate from the 12px text until the look's face can be measured.
  const [size, setSize] = useState({ width: text.length * 6.6, height: 15 });
  useLayoutEffect(() => {
    const measure = () => {
      const box = textRef.current?.getBBox();
      if (box && box.width > 0)
        setSize((current) =>
          current.width === box.width && current.height === box.height
            ? current
            : { width: box.width, height: box.height },
        );
    };
    measure();
    // The look's face may load after the first paint; measure it again then.
    let active = true;
    void document.fonts.ready.then(() => {
      if (active) measure();
    });
    return () => {
      active = false;
    };
  }, [text]);
  const width = size.width + LABEL_PADDING.x * 2;
  const height = size.height + LABEL_PADDING.y * 2;
  return (
    <EdgeLabelRenderer>
      <div
        data-sandbox-edge-label={id}
        data-trace={trace ?? undefined}
        aria-hidden="true"
        className="nodrag nopan pointer-events-none absolute top-0 left-0"
        style={{
          transform: `translate(-50%, -50%) translate(${x}px, ${y}px)`,
          // Above the tables (z-index 1), which React Flow draws later.
          zIndex: 2,
        }}
      >
        <svg width={width} height={height} overflow="visible" className="block">
          <rect
            // Corners come from the look's --radius (globals.css).
            data-sandbox-part="line-label"
            x={0.5}
            y={0.5}
            width={width - 1}
            height={height - 1}
            rx={6}
            ry={6}
            fill="var(--canvas-label-fill)"
            stroke="var(--canvas-label-frame)"
            strokeWidth={1}
          />
          <text
            ref={textRef}
            x={width / 2}
            y={height / 2}
            textAnchor="middle"
            dominantBaseline="central"
            fontSize={12}
            fontWeight={500}
            // A relationship's label takes its line's action ink.
            fill={handoff ? "var(--canvas-label-ink)" : "var(--action-text)"}
          >
            {text}
          </text>
        </svg>
      </div>
    </EdgeLabelRenderer>
  );
}

function RelationshipEdgeView({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps<RelationshipFlowEdge>) {
  const actions = useCanvasActions();
  const trace = useTraceMark(actions.trace, id);
  const stop = useLineLabelStop(actions.labels, id);
  const selected = data?.selected ?? false;
  const handoff = data?.handoff ?? false;
  const line = relationshipLineAttrs(selected, handoff);
  const [path, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    ...LINE_PATH,
  });
  // The label sits at its placed share of the line (sandbox-canvas-labels.ts).
  const label = data?.label ?? "";
  const at = label === "" ? null : pointAlong(pathPoints(path), stop);
  const arrow =
    trace === "on"
      ? "trace"
      : selected
        ? "selected"
        : handoff
          ? "handoff"
          : "relationship";
  return (
    <>
      <g data-sandbox-edge={id} data-trace={trace ?? undefined}>
        {/* A wide transparent stroke so a 1.6px line is easy to click. */}
        <path d={path} fill="none" stroke="transparent" strokeWidth={16} />
        <path
          d={path}
          fill="none"
          data-sandbox-line={line["data-sandbox-line"]}
          data-sandbox-edge-kind={line["data-sandbox-edge-kind"]}
          stroke={line.stroke}
          strokeWidth={line.strokeWidth}
          strokeDasharray={line.strokeDasharray || undefined}
          strokeLinecap="round"
          markerEnd={`url(#sandbox-arrow-${arrow})`}
        />
      </g>
      {label !== "" ? (
        <LineLabel
          id={id}
          x={at?.x ?? labelX}
          y={at?.y ?? labelY}
          text={label}
          handoff={handoff}
          trace={trace}
        />
      ) : null}
    </>
  );
}

export const SANDBOX_NODE_TYPES = {
  department: memo(DepartmentNodeView),
  module: memo(ModuleNodeView),
};

export const SANDBOX_EDGE_TYPES = {
  relationship: memo(RelationshipEdgeView),
};
