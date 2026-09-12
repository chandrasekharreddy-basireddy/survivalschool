"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { ThemeToggle } from "@/components/ThemeToggle";
import { isAdmin, isInstructor } from "@/lib/roles";
import { useHideChrome } from "@/lib/useFullscreen";

const COLLAPSE_STORAGE_KEY = "survivalschool:sidebar-collapsed";

function LogoMark() {
  return (
    <span className="relative inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-ink-700 bg-ink-900 shadow-sm">
      <svg viewBox="0 0 40 40" fill="none" className="h-6 w-6" aria-hidden="true">
        <circle cx="20" cy="21" r="14" stroke="rgb(var(--accent-2))" strokeWidth="2.4" />
        <path d="M20 8 32 30H8L20 8Z" fill="rgb(var(--brand))" />
        <rect x="15.5" y="21" width="9" height="9" rx="1.4" fill="#f4f6fb" />
      </svg>
    </span>
  );
}

// One consistent icon set for the whole nav — same 24x24 viewBox, 1.75 stroke,
// no fill, matching the pre-existing Bell/Menu icons in the old top nav so a
// collapsed (icon-only) sidebar reads cleanly.
const ICONS: Record<string, (props: { className?: string }) => React.ReactElement> = {
  contests: (p) => <svg {...p} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5h7.5v3a3.75 3.75 0 1 1-7.5 0v-3Z" /><path strokeLinecap="round" strokeLinejoin="round" d="M8.25 6H4.5v1.5a3 3 0 0 0 3 3M15.75 6h3.75v1.5a3 3 0 0 1-3 3M12 12v3m-3 3.75h6M9.75 18.75h4.5" /></svg>,
  elimination: (p) => <svg {...p} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M13.5 3 4.5 13.5h6L9 21l10.5-11.25h-6L13.5 3Z" /></svg>,
  dashboard: (p) => <svg {...p} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M3.75 12 12 3.75 20.25 12M5.25 10.5v9a.75.75 0 0 0 .75.75H10.5v-6h3v6h4.5a.75.75 0 0 0 .75-.75v-9" /></svg>,
  classrooms: (p) => <svg {...p} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="m12 3 9 4.5-9 4.5-9-4.5L12 3Z" /><path strokeLinecap="round" strokeLinejoin="round" d="M6.75 10.5v4.5c0 1 2.5 3 5.25 3s5.25-2 5.25-3v-4.5M21 7.5v6" /></svg>,
  practice: (p) => <svg {...p} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M12 6.75C10.5 5.25 8 4.5 5.25 4.5v13.5c2.75 0 5.25.75 6.75 2.25M12 6.75c1.5-1.5 4-2.25 6.75-2.25v13.5c-2.75 0-5.25.75-6.75 2.25M12 6.75v13.5" /></svg>,
  ranks: (p) => <svg {...p} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M3.75 19.5h16.5M6.75 19.5v-6m5.25 6V9m5.25 10.5v-4.5" /></svg>,
  chat: (p) => <svg {...p} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.297-1.053 2.35-2.35 2.35H15l-3 3v-3H6.1a2.35 2.35 0 0 1-2.35-2.35v-4.286c0-.97.616-1.813 1.5-2.097m15-4.261a2.35 2.35 0 0 0-2.35-2.35H6.1a2.35 2.35 0 0 0-2.35 2.35v3.75c0 1.298 1.053 2.35 2.35 2.35h11.8c1.297 0 2.35-1.052 2.35-2.35v-3.75Z" /></svg>,
  connections: (p) => <svg {...p} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M15 19.5v-1.5a3.75 3.75 0 0 0-3.75-3.75h-3A3.75 3.75 0 0 0 4.5 18v1.5M18 19.5v-1.5a3.75 3.75 0 0 0-2.25-3.435M13.125 6.75a3 3 0 1 1-6 0 3 3 0 0 1 6 0ZM17.25 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" /></svg>,
  aiPractice: (p) => <svg {...p} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.456-2.456L14.25 6l1.035-.259a3.375 3.375 0 0 0 2.456-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456Z" /></svg>,
  aiTutor: (p) => <svg {...p} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5h7.5v3a3.75 3.75 0 1 1-7.5 0v-3Z" opacity="0" /><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12a7.5 7.5 0 1 1 4.5 6.875L4.5 20.25l1.375-4.5A7.464 7.464 0 0 1 4.5 12Z" /><path strokeLinecap="round" strokeLinejoin="round" d="M9 10.5h6M9 13.5h3.75" /></svg>,
  instructor: (p) => <svg {...p} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" /></svg>,
  admin: (p) => <svg {...p} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75m5.25 1.5c0 5.25-3.75 8.25-8.25 9.75-4.5-1.5-8.25-4.5-8.25-9.75V6l8.25-3 8.25 3v5.25Z" /></svg>,
  applyTeach: (p) => <svg {...p} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487 18.55 2.8a1.875 1.875 0 1 1 2.65 2.65L9.75 16.9l-4.5 1.125 1.125-4.5 10.487-10.038Z" /><path strokeLinecap="round" strokeLinejoin="round" d="M19.5 12.75V19.5a1.875 1.875 0 0 1-1.875 1.875H5.625A1.875 1.875 0 0 1 3.75 19.5V6.375A1.875 1.875 0 0 1 5.625 4.5h6.75" /></svg>,
  bell: (p) => <svg {...p} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0" /></svg>,
};

function MenuIcon({ open, className }: { open: boolean; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} className={className}>
      {open ? <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" /> : <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5M3.75 17.25h16.5" />}
    </svg>
  );
}

// Collapse/expand chevron — rotates rather than swapping icons, so the
// direction always visually matches which way the panel is about to move.
function ChevronIcon({ collapsed, className }: { collapsed: boolean; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} className={`${className ?? ""} transition-transform duration-200 ${collapsed ? "rotate-180" : ""}`}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.5 8.25 12 15 4.5" />
    </svg>
  );
}

export function Sidebar() {
  const { user, loading, logout } = useAuth();
  const pathname = usePathname();
  const isFullscreen = useHideChrome();
  const [mobileOpen, setMobileOpen] = useState(false);
  // Starts expanded on every load (including the very first paint) rather
  // than reading localStorage synchronously — that would mismatch between
  // server and client render and trigger a hydration warning. The effect
  // below applies the stored preference a tick after mount instead.
  const [collapsed, setCollapsed] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      setCollapsed(window.localStorage.getItem(COLLAPSE_STORAGE_KEY) === "1");
    } catch {
      /* localStorage unavailable (locked-down browser context) — stay expanded */
    }
    setHydrated(true);
  }, []);

  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(COLLAPSE_STORAGE_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  };

  const closeMobile = () => setMobileOpen(false);
  const canTeach = isInstructor(user);
  const canAdmin = isAdmin(user);

  const links = [
    ["/contests", "Contests", ICONS.contests, true],
    ["/elimination", "Elimination", ICONS.elimination, !!user],
    ["/dashboard", "Dashboard", ICONS.dashboard, !!user],
    ["/classrooms", "Classrooms", ICONS.classrooms, !!user],
    ["/practice", "Practice", ICONS.practice, !!user],
    ["/leaderboard", "Ranks", ICONS.ranks, !!user],
    ["/chat", "Chat", ICONS.chat, !!user],
    ["/follows", "Connections", ICONS.connections, !!user],
    ["/ai-practice", "AI Practice", ICONS.aiPractice, !!user],
    ["/ai-assistant", "AI Tutor", ICONS.aiTutor, !!user],
    ["/instructor", "Question bank", ICONS.instructor, canTeach],
    ["/admin", "Admin", ICONS.admin, canAdmin],
    ["/register/instructor", "Apply to teach", ICONS.applyTeach, !!user && !canTeach],
  ] as const;

  const isActive = (href: string) => pathname === href || (href !== "/" && pathname.startsWith(href + "/"));

  // A locked-down exam in fullscreen has no use for the sidebar — it's dead
  // space at best and, worse, a way out of the exam via its nav links.
  if (isFullscreen) return null;

  return (
    <>
      {/* Mobile top bar — the sidebar itself is an off-canvas drawer below
          lg, so this is the only persistent chrome on small screens: logo,
          theme, and the trigger that opens the drawer. */}
      <header className="fixed inset-x-0 top-0 z-40 flex h-14 items-center gap-2 border-b border-ink-700/80 bg-ink-950 px-3 sm:px-5 lg:hidden">
        <Link href="/" className="flex shrink-0 items-center gap-2.5 text-sm font-bold tracking-tight text-fg">
          <LogoMark />
          <span className="text-[0.9rem] tracking-tight">
            Survival<span className="text-brand-600 dark:text-brand-400"> School</span>
          </span>
        </Link>
        <div className="ml-auto flex items-center gap-1.5">
          <ThemeToggle />
          <button
            onClick={() => setMobileOpen(true)}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-ink-700 bg-ink-900 text-fg-muted hover:text-fg"
            aria-label="Open menu"
            aria-expanded={mobileOpen}
          >
            <MenuIcon open={false} className="h-5 w-5" />
          </button>
        </div>
      </header>

      {/* Backdrop — mobile drawer only */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 bg-black/50 lg:hidden" onClick={closeMobile} aria-hidden="true" />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex h-screen w-72 shrink-0 flex-col border-r border-ink-700/80 bg-ink-950 transition-transform duration-200 lg:sticky lg:top-0 lg:z-auto lg:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        } ${!hydrated ? "lg:w-64" : collapsed ? "lg:w-[4.5rem]" : "lg:w-64"}`}
      >
        <div className={`flex h-14 shrink-0 items-center gap-2.5 border-b border-ink-700/80 px-4 ${collapsed && hydrated ? "lg:justify-center lg:px-0" : ""}`}>
          <Link href="/" onClick={closeMobile} className="flex shrink-0 items-center gap-2.5 text-sm font-bold tracking-tight text-fg">
            <LogoMark />
            <span className={`text-[0.9rem] tracking-tight ${collapsed && hydrated ? "lg:hidden" : ""}`}>
              Survival<span className="text-brand-600 dark:text-brand-400"> School</span>
            </span>
          </Link>
          <button onClick={closeMobile} className="ml-auto inline-flex h-8 w-8 items-center justify-center rounded-lg text-fg-muted hover:bg-ink-800 hover:text-fg lg:hidden" aria-label="Close menu">
            <MenuIcon open className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto px-2.5 py-3">
          {links.map(([href, label, Icon, visible]) =>
            !visible ? null : (
              <Link
                key={href}
                href={href}
                onClick={closeMobile}
                title={collapsed && hydrated ? label : undefined}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${collapsed && hydrated ? "lg:justify-center lg:px-0" : ""} ${
                  isActive(href) ? "bg-ink-800 text-fg" : "text-fg-muted hover:bg-ink-800/70 hover:text-fg"
                }`}
              >
                <Icon className="h-5 w-5 shrink-0" />
                <span className={collapsed && hydrated ? "lg:hidden" : ""}>{label}</span>
              </Link>
            )
          )}
        </nav>

        <div className="shrink-0 border-t border-ink-700/80 p-2.5">
          {loading ? null : user ? (
            <div className="space-y-0.5">
              <Link
                href="/notifications"
                onClick={closeMobile}
                title={collapsed && hydrated ? "Notifications" : undefined}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-fg-muted hover:bg-ink-800/70 hover:text-fg ${collapsed && hydrated ? "lg:justify-center lg:px-0" : ""}`}
              >
                <ICONS.bell className="h-5 w-5 shrink-0" />
                <span className={collapsed && hydrated ? "lg:hidden" : ""}>Notifications</span>
              </Link>
              <Link
                href="/profile"
                onClick={closeMobile}
                title={collapsed && hydrated ? user.full_name : undefined}
                className={`flex items-center gap-3 truncate rounded-lg px-3 py-2 text-sm font-medium text-fg-muted hover:bg-ink-800/70 hover:text-fg ${collapsed && hydrated ? "lg:justify-center lg:px-0" : ""}`}
              >
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-ink-800 text-[0.65rem] font-bold text-fg">
                  {user.full_name?.[0]?.toUpperCase() ?? "?"}
                </span>
                <span className={`truncate ${collapsed && hydrated ? "lg:hidden" : ""}`}>{user.full_name}</span>
              </Link>
              <div className={`flex items-center gap-2 px-3 pt-1 ${collapsed && hydrated ? "lg:flex-col lg:px-0" : ""}`}>
                <div className={collapsed && hydrated ? "lg:hidden" : ""}><ThemeToggle /></div>
                <button onClick={() => { logout(); closeMobile(); }} className={`btn-secondary !min-h-8 flex-1 !px-2.5 !py-1.5 text-xs ${collapsed && hydrated ? "lg:hidden" : ""}`}>
                  Sign out
                </button>
              </div>
            </div>
          ) : (
            <div className={`space-y-1.5 ${collapsed && hydrated ? "lg:hidden" : ""}`}>
              <Link href="/login" onClick={closeMobile} className="btn-secondary !min-h-8 w-full !px-2.5 !py-1.5 text-xs">Sign in</Link>
              <Link href="/register" onClick={closeMobile} className="btn-primary !min-h-8 w-full !px-2.5 !py-1.5 text-xs">Join</Link>
            </div>
          )}
          <button
            onClick={toggleCollapsed}
            className="mt-1.5 hidden w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-fg-muted hover:bg-ink-800/70 hover:text-fg lg:flex"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            <ChevronIcon collapsed={collapsed} className="h-4 w-4" />
            <span className={collapsed && hydrated ? "lg:hidden" : ""}>Collapse</span>
          </button>
        </div>
      </aside>
    </>
  );
}
