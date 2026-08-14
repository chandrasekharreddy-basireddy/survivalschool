import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto flex min-h-[60vh] max-w-lg flex-col items-center justify-center px-6 text-center">
      <p className="text-sm font-semibold uppercase tracking-widest text-brand-600 dark:text-brand-400">404</p>
      <h1 className="mt-2 text-2xl font-bold text-fg">Page not found</h1>
      <p className="mt-2 text-sm text-fg-muted">
        The page you&apos;re looking for doesn&apos;t exist or may have moved.
      </p>
      <div className="mt-6 flex gap-3">
        <Link href="/dashboard" className="btn-primary">Go to dashboard</Link>
        <Link href="/courses" className="btn-secondary">Browse courses</Link>
      </div>
    </div>
  );
}
