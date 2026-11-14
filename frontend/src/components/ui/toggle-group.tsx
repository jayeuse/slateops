"use client";

import * as React from "react";
import { Toggle as TogglePrimitive } from "@base-ui/react/toggle";
import { ToggleGroup as ToggleGroupPrimitive } from "@base-ui/react/toggle-group";
import { type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import {
  pillClass,
  pillOptionHeightClass,
  pillRailClass,
} from "@/components/ui/pill";

import { toggleVariants } from "@/components/ui/toggle";

// A single-select filter: a sunken rail whose pressed item is raised, in the
// action ink, and bold, so the choice reads in every look; idle items are
// muted, so pressed differs in brightness as well as hue. The raised pill is
// one element per group that glides to the chosen item (SegmentedPill). The
// group is the pill's stacking layer, so on its way it passes under every
// item's words; a focused item is not lifted (items here never overlap), or
// the pill inside it would cover its neighbors.
const segmentedGroup = `isolate flex w-full flex-wrap gap-1 ${pillRailClass}`;
const segmentedItem = `relative transition-colors focus:z-auto focus-visible:z-auto focus-visible:ring-0 h-auto ${pillOptionHeightClass} min-w-0 flex-1 px-3 py-1 text-sm whitespace-normal text-muted-foreground hover:bg-transparent hover:text-foreground aria-pressed:bg-transparent aria-pressed:font-semibold aria-pressed:text-action-text`;

const ToggleGroupContext = React.createContext<
  VariantProps<typeof toggleVariants> & {
    spacing?: number;
    orientation?: "horizontal" | "vertical";
    /** The group's own pill name, so pills of two groups never trade places. */
    pillId?: string;
  }
>({
  size: "default",
  variant: "default",
  spacing: 2,
  orientation: "horizontal",
});

function ToggleGroup({
  className,
  variant,
  size,
  spacing = 2,
  orientation = "horizontal",
  children,
  ...props
}: ToggleGroupPrimitive.Props &
  VariantProps<typeof toggleVariants> & {
    spacing?: number;
    orientation?: "horizontal" | "vertical";
  }) {
  const pillId = React.useId();
  return (
    <ToggleGroupPrimitive
      data-slot="toggle-group"
      data-variant={variant}
      data-pill-rail={variant === "segmented" ? "" : undefined}
      data-size={size}
      data-spacing={spacing}
      data-orientation={orientation}
      style={{ "--gap": spacing } as React.CSSProperties}
      className={cn(
        "group/toggle-group flex w-fit flex-row items-center gap-[--spacing(var(--gap))] rounded-lg data-[orientation=vertical]:flex-col data-[orientation=vertical]:items-stretch data-[size=sm]:rounded-[min(var(--radius-md),10px)]",
        variant === "segmented" && segmentedGroup,
        className,
      )}
      {...props}
    >
      <ToggleGroupContext.Provider
        value={{ variant, size, spacing, orientation, pillId }}
      >
        {children}
      </ToggleGroupContext.Provider>
    </ToggleGroupPrimitive>
  );
}

function ToggleGroupItem({
  className,
  children,
  variant = "default",
  size = "default",
  ...props
}: TogglePrimitive.Props & VariantProps<typeof toggleVariants>) {
  const context = React.useContext(ToggleGroupContext);

  return (
    <TogglePrimitive
      data-slot="toggle-group-item"
      data-variant={context.variant || variant}
      data-pill-option={
        (context.variant || variant) === "segmented" ? "" : undefined
      }
      data-size={context.size || size}
      data-spacing={context.spacing}
      className={cn(
        "shrink-0 group-data-[spacing=0]/toggle-group:rounded-none group-data-[spacing=0]/toggle-group:px-2 focus:z-10 focus-visible:z-10 group-data-[spacing=0]/toggle-group:has-data-[icon=inline-end]:pr-1.5 group-data-[spacing=0]/toggle-group:has-data-[icon=inline-start]:pl-1.5 group-data-[orientation=horizontal]/toggle-group:data-[spacing=0]:first:rounded-l-lg group-data-[orientation=vertical]/toggle-group:data-[spacing=0]:first:rounded-t-lg group-data-[orientation=horizontal]/toggle-group:data-[spacing=0]:last:rounded-r-lg group-data-[orientation=vertical]/toggle-group:data-[spacing=0]:last:rounded-b-lg group-data-[orientation=horizontal]/toggle-group:data-[spacing=0]:data-[variant=outline]:border-l-0 group-data-[orientation=vertical]/toggle-group:data-[spacing=0]:data-[variant=outline]:border-t-0 group-data-[orientation=horizontal]/toggle-group:data-[spacing=0]:data-[variant=outline]:first:border-l group-data-[orientation=vertical]/toggle-group:data-[spacing=0]:data-[variant=outline]:first:border-t",
        toggleVariants({
          variant: context.variant || variant,
          size: context.size || size,
        }),
        (context.variant || variant) === "segmented" && segmentedItem,
        className,
      )}
      {...props}
      render={
        (context.variant || variant) === "segmented"
          ? (buttonProps, state) => (
              <button {...buttonProps}>
                {state.pressed ? <SegmentedPill /> : null}
                {buttonProps.children}
              </button>
            )
          : props.render
      }
    >
      {children}
    </TogglePrimitive>
  );
}

const pillClassName = `absolute inset-0 -z-10 ${pillClass}`;

function StillPill() {
  return (
    <span
      aria-hidden="true"
      data-slot="segmented-pill"
      data-pill=""
      className={pillClassName}
    />
  );
}

// If the Motion pill cannot load (an old tab after a deploy), the still pill
// stays; the choice still reads, it only does not glide.
const MotionSegmentedPill = React.lazy(() =>
  import("./segmented-pill").catch(() => ({ default: StillPill })),
);

/**
 * The raised pill of a segmented group. Each group has one: choosing another
 * item moves it there over --motion-base with --ease-in-out (a move, not an
 * arrival), so the eye follows the choice. Under Reduce motion it jumps. A
 * control in the group that is not a ToggleGroupItem (the "More" menu button
 * of a quick filter) renders it while its choice is current. Until Motion
 * loads, the same pill stands still in place, so nothing flashes.
 */
function SegmentedPill() {
  const { pillId } = React.useContext(ToggleGroupContext);
  return (
    <React.Suspense fallback={<StillPill />}>
      <MotionSegmentedPill id={pillId ?? ""} className={pillClassName} />
    </React.Suspense>
  );
}

export { SegmentedPill, ToggleGroup, ToggleGroupItem };
