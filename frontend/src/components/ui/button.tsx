import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentPropsWithRef, MouseEvent, ReactNode } from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  // On a touch screen the tap area reaches 44px tall (and 4px wider each
  // side) without a bigger button: a transparent ::after (Human Owner,
  // 2026-11-14). Only for a coarse pointer: the ::after reaches past the
  // button and would widen a scrolling list, and a mouse needs no more.
  // A busy button (pending) keeps its color and shows a progress cursor.
  // A blocked button (aria-disabled, which keeps it focusable to say why)
  // fades its fill and text only, so its focus ring keeps full strength.
  "relative pointer-coarse:after:absolute pointer-coarse:after:-inset-x-1 pointer-coarse:after:top-[min(0px,calc((100%-2.75rem)/2))] pointer-coarse:after:bottom-[min(0px,calc((100%-2.75rem)/2))] data-pending:cursor-progress data-pending:opacity-100 inline-flex items-center justify-center gap-2 rounded-[var(--radius)] text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50 aria-disabled:cursor-not-allowed [&_svg]:size-4",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground hover:bg-[color-mix(in_srgb,var(--primary)_86%,var(--ink))] aria-disabled:not-data-pending:bg-primary/50",
        secondary:
          "bg-secondary text-secondary-foreground hover:over-tint-hover aria-disabled:not-data-pending:bg-none aria-disabled:not-data-pending:text-secondary-foreground/50",
        ghost:
          "text-foreground hover:bg-tint-hover aria-disabled:not-data-pending:bg-transparent aria-disabled:not-data-pending:text-foreground/50",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-[color-mix(in_srgb,var(--destructive)_86%,var(--ink))] aria-disabled:not-data-pending:bg-destructive/50",
        // Themes set --button-edge and --button-ink; a call site's own
        // border or text classes still win.
        outline:
          "border border-[color:var(--button-edge,var(--border))] bg-card text-[color:var(--button-ink)] hover:over-tint-hover aria-disabled:not-data-pending:bg-none aria-disabled:not-data-pending:text-[color:color-mix(in_oklab,var(--button-ink)_50%,transparent)]",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 px-3 text-xs",
        lg: "h-11 px-5",
        icon: "size-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends ComponentPropsWithRef<"button">, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  /** The action is running: the button says so (`aria-busy`), keeps its
   * width and the keyboard focus, and ignores clicks (`aria-disabled`). */
  pending?: boolean;
  /** Shown while pending, for example "Saving…". The button keeps the
   * width of its longer label, so the layout never jumps. */
  pendingLabel?: ReactNode;
}

const ignoreWhileBusy = (event: MouseEvent<HTMLButtonElement>) =>
  event.preventDefault();

export function Button({
  className,
  variant,
  size,
  asChild = false,
  pending = false,
  pendingLabel,
  disabled,
  children,
  onClick,
  ...props
}: ButtonProps) {
  const Component = asChild ? Slot : "button";
  // Both labels share one grid cell; the hidden one keeps its width and is
  // left out of the accessible name (visibility: hidden).
  const content =
    pendingLabel === undefined || asChild ? (
      children
    ) : (
      <span className="grid">
        <span
          className={cn(
            "col-start-1 row-start-1 inline-flex items-center justify-center gap-2",
            pending && "invisible",
          )}
        >
          {children}
        </span>
        <span
          className={cn(
            "col-start-1 row-start-1 inline-flex items-center justify-center gap-2",
            !pending && "invisible",
          )}
        >
          {pendingLabel}
        </span>
      </span>
    );

  return (
    <Component
      data-slot="button"
      data-variant={variant ?? "default"}
      data-size={size ?? "default"}
      className={cn(buttonVariants({ variant, size, className }))}
      // Busy outranks disabled: a call site's own condition often turns true
      // while the action runs, and native disabled would drop the focus.
      disabled={pending ? undefined : disabled}
      aria-busy={pending || undefined}
      data-pending={pending || undefined}
      {...props}
      // Busy: not `disabled`, which would drop the keyboard focus, but
      // aria-disabled with every click ignored (also a form's Enter submit).
      aria-disabled={pending ? true : props["aria-disabled"]}
      onClick={pending ? ignoreWhileBusy : onClick}
    >
      {content}
    </Component>
  );
}
