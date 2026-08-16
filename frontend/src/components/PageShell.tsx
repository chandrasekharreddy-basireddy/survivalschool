import type { ReactNode } from "react";

export function PageShell({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`page-frame ${className}`}>{children}</div>;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && (
          <p className="mb-2 text-[0.68rem] font-extrabold uppercase tracking-[0.18em] text-brand-400">
            {eyebrow}
          </p>
        )}
        <h1>{title}</h1>
        {description && (
          <p className="mt-2 max-w-2xl text-sm text-fg-muted sm:text-[0.95rem]">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex w-full flex-wrap gap-2 sm:w-auto">{actions}</div>}
    </header>
  );
}

export function SectionCard({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`section-card ${className}`}>{children}</section>;
}
