import * as React from "react";
import { AlertTriangle, CircleAlert, Info } from "lucide-react";
import { cn } from "@/lib/utils";

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("animate-pulse rounded-md bg-sunken", className)} {...props} />;
}

/** A bordered surface. Used for tables and charts — not for every block of content. */
export function Panel({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <section className={cn("min-w-0 rounded-lg border border-line bg-surface", className)} {...props} />;
}

export function PanelHeader({
  title,
  description,
  actions,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex flex-wrap items-start justify-between gap-3 px-4 pb-3 pt-4", className)}>
      <div className="min-w-0">
        <h2 className="text-lg font-semibold">{title}</h2>
        {description && <p className="mt-0.5 text-sm text-ink-2">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

const calloutTone = {
  info: { box: "border-info/25 bg-info-soft", icon: Info, iconClass: "text-info" },
  warn: { box: "border-warn/30 bg-warn-soft", icon: AlertTriangle, iconClass: "text-warn" },
  error: { box: "border-down/30 bg-down-soft", icon: CircleAlert, iconClass: "text-down" },
};

export function Callout({
  tone = "info",
  title,
  children,
  action,
  className,
}: {
  tone?: keyof typeof calloutTone;
  title: React.ReactNode;
  children?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  const t = calloutTone[tone];
  const Icon = t.icon;
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn("flex items-start gap-3 rounded-lg border px-4 py-3", t.box, className)}
    >
      <Icon className={cn("mt-0.5 size-4 shrink-0", t.iconClass)} />
      <div className="min-w-0 flex-1">
        <p className="font-medium text-ink">{title}</p>
        {children && <div className="mt-0.5 text-sm text-ink-2">{children}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
  className,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center px-6 py-14 text-center", className)}>
      <div className="mb-3 rounded-full bg-sunken p-3 text-muted">
        <Icon className="size-5" />
      </div>
      <p className="text-lg font-semibold">{title}</p>
      {children && <div className="mt-1 max-w-md text-ink-2">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/** Key/value line used in summaries and the analysis sidebar. */
export function Stat({
  label,
  value,
  sub,
  className,
}: {
  label: React.ReactNode;
  value: React.ReactNode;
  sub?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <dt className="text-sm text-ink-2">{label}</dt>
      <dd className="mt-1 text-xl font-semibold tracking-tight">{value}</dd>
      {sub && <dd className="mt-0.5 text-sm text-ink-2">{sub}</dd>}
    </div>
  );
}
