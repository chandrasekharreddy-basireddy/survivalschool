const SIZES = {
  sm: { box: "h-4 w-4", border: "border-2" },
  md: { box: "h-8 w-8", border: "border-[3px]" },
  lg: { box: "h-10 w-10", border: "border-4" },
} as const;

interface PageLoaderProps {
  /** "lg" fills a whole page/section (the common case); "md" sits inline in
   * a card or list; "sm" sits next to a line of text or inside a button. */
  size?: keyof typeof SIZES;
  label?: string;
  className?: string;
}

/** The app's one loading motif: a rounded three-colour ring, used in place
 * of a bare "Loading…" string everywhere something is loading — a page, a
 * section, a list. See .page-loader-ring in globals.css for the animation
 * itself (respects prefers-reduced-motion globally). Root is a <span> (not
 * a <div>) so it's always valid to drop inline, including inside a <p>. */
export function PageLoader({ size = "lg", label, className = "" }: PageLoaderProps) {
  const { box, border } = SIZES[size];
  return (
    <span
      role="status"
      aria-live="polite"
      className={`inline-flex items-center gap-2.5 ${size === "lg" ? "w-full flex-col justify-center py-16" : ""} ${className}`}
    >
      <span className={`page-loader-ring ${box} ${border}`} aria-hidden="true" />
      <span className="text-sm text-fg-subtle">{label ?? "Loading…"}</span>
    </span>
  );
}

export default PageLoader;
