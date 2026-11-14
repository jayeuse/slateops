import { cn } from "@/lib/utils";

/**
 * The product's one mark (SO-M1, docs/specs/signed-out-pages.md): the
 * classes of the `WorkspaceLogo` fallback, so the product mark and the
 * default organization mark look the same. Decorative: the words beside it
 * name the product.
 */
export function ProductMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "bg-foreground text-background grid size-8 shrink-0 place-items-center rounded-md text-xs font-bold",
        className,
      )}
    >
      SO
    </span>
  );
}
