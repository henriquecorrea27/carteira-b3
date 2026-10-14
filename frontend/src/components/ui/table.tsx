import * as React from "react";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { cn } from "@/lib/utils";

export function Table({ className, ...props }: React.TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className="relative w-full overflow-x-auto">
      <table className={cn("w-full border-collapse text-base", className)} {...props} />
    </div>
  );
}

export function THead({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn("[&_tr]:border-b [&_tr]:border-line", className)} {...props} />;
}

export function TBody({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("[&_tr:last-child]:border-0", className)} {...props} />;
}

export function TR({ className, ...props }: React.HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("border-b border-line transition-colors", className)} {...props} />;
}

export function TH({
  className,
  numeric,
  ...props
}: React.ThHTMLAttributes<HTMLTableCellElement> & { numeric?: boolean }) {
  return (
    <th
      className={cn(
        "h-9 whitespace-nowrap px-3 text-xs font-medium text-muted first:pl-4 last:pr-4",
        numeric ? "text-right" : "text-left",
        className,
      )}
      {...props}
    />
  );
}

export function TD({
  className,
  numeric,
  ...props
}: React.TdHTMLAttributes<HTMLTableCellElement> & { numeric?: boolean }) {
  return (
    <td
      className={cn(
        "h-11 whitespace-nowrap px-3 first:pl-4 last:pr-4",
        numeric && "num text-right",
        className,
      )}
      {...props}
    />
  );
}

export type SortDir = "asc" | "desc";

/** Sortable header button; aria-sort lives on the <th>. */
export function SortHeader({
  label,
  active,
  dir,
  onClick,
  numeric,
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
  numeric?: boolean;
}) {
  const Icon = !active ? ArrowUpDown : dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1 rounded-sm hover:text-ink",
        numeric && "flex-row-reverse",
        active && "text-ink",
      )}
    >
      {label}
      <Icon className={cn("size-3", !active && "opacity-0 group-hover/th:opacity-60")} />
    </button>
  );
}
