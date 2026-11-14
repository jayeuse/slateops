"use client";
import { Tabs as TabsPrimitive } from "@base-ui/react/tabs";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";
import {
  pillClass,
  pillOptionHeightClass,
  pillRailClass,
} from "@/components/ui/pill";
export function Tabs({
  className,
  ...props
}: Omit<ComponentProps<typeof TabsPrimitive.Root>, "className"> & {
  className?: string;
}) {
  return (
    <TabsPrimitive.Root
      className={cn("flex flex-col gap-4", className)}
      {...props}
    />
  );
}
export function TabsList({
  className,
  children,
  ...props
}: Omit<ComponentProps<typeof TabsPrimitive.List>, "className"> & {
  className?: string;
}) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      className={cn(
        "text-muted-foreground relative inline-flex w-fit items-center gap-1",
        pillRailClass,
        className,
      )}
      {...props}
    >
      {children}
      {/* The active mark is one element that glides between tabs; each look
          styles it (a lifted surface, a marker line, an ink rule, a steel
          tab). */}
      <TabsPrimitive.Indicator
        data-slot="tabs-indicator"
        className={cn(
          "absolute top-(--active-tab-top) left-(--active-tab-left) h-(--active-tab-height) w-(--active-tab-width) transition-[left,top,width,height] duration-(--motion-base) ease-(--ease-out) motion-reduce:transition-none",
          pillClass,
        )}
      />
    </TabsPrimitive.List>
  );
}
export function TabsTrigger({
  className,
  ...props
}: Omit<ComponentProps<typeof TabsPrimitive.Tab>, "className"> & {
  className?: string;
}) {
  return (
    <TabsPrimitive.Tab
      data-slot="tabs-trigger"
      className={cn(
        pillOptionHeightClass,
        "focus-visible:outline-ring data-active:text-action-text relative z-[1] inline-flex items-center justify-center rounded-sm px-3 py-1 text-sm font-medium transition-colors duration-(--motion-fast) outline-none focus-visible:outline-2 disabled:opacity-50 data-active:font-semibold",
        className,
      )}
      {...props}
    />
  );
}
export function TabsContent({
  className,
  ...props
}: Omit<ComponentProps<typeof TabsPrimitive.Panel>, "className"> & {
  className?: string;
}) {
  return (
    <TabsPrimitive.Panel
      className={cn(
        "focus-visible:outline-ring outline-none focus-visible:outline-2",
        className,
      )}
      {...props}
    />
  );
}
