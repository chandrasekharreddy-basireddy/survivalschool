import type { ReactNode } from "react";

export function PageShell({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`mx-auto w-full max-w-7xl px-3 py-6 sm:px-5 sm:py-8 lg:px-6 lg:py-10 ${className}`}>{children}</div>;
}

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-col gap-4 border-b border-ink-800 pb-5 sm:mb-8 sm:flex-row sm:items-end sm:justify-between sm:pb-6">
      <div className="min-w-0">
        {eyebrow && <p className="mb-2 text-[0.7rem] font-bold uppercase tracking-[0.18em] text-brand-400">{eyebrow}</p>}
        <h1 className="text-balance text-2xl font-bold tracking-tight text-fg sm:text-3xl">{title}</h1>
        {description && <p className="mt-2 max-w-2xl text-sm leading-6 text-fg-muted sm:text-base">{description}</p>}
      </div>
      {actions && <div className="flex w-full flex-wrap gap-2 sm:w-auto">{actions}</div>}
    </header>
  );
}

export function SectionCard({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-xl border border-ink-800 bg-ink-950/75 p-4 shadow-[0_10px_30px_rgba(0,0,0,.18)] sm:p-5 ${className}`}>{children}</section>;
}
