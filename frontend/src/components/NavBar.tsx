"use client";

import Link from "next/link";
import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { ThemeToggle } from "@/components/ThemeToggle";
import { SearchBar } from "@/components/SearchBar";
import { hasRole, isAdmin, isInstructor } from "@/lib/roles";

const navLinkClass = "rounded-md px-2 py-1.5 text-[0.82rem] font-medium text-fg-muted transition-colors hover:bg-ink-900/80 hover:text-fg";

function LogoMark() {
  return (
    <span className="relative inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-brand-500/30 bg-ink-900">
      <svg viewBox="0 0 40 40" fill="none" className="h-7 w-7" aria-hidden="true">
        <circle cx="20" cy="20" r="15" stroke="#e83385" strokeWidth="2.2" />
        <path d="M20 8 31 27H9L20 8Z" stroke="#48d5c4" strokeWidth="2.2" strokeLinejoin="round" />
        <rect x="15.3" y="15.3" width="9.4" height="9.4" stroke="#fff" strokeWidth="2" />
      </svg>
    </span>
  );
}

export function NavBar() {
  const { user, loading, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const closeMobile = () => setMobileOpen(false);
  const canTeach = isInstructor(user);
  const canAdmin = isAdmin(user);
  const isPrivileged = hasRole(user, ["ADMIN", "SUPER_ADMIN", "INSTRUCTOR", "MODERATOR", "SUPPORT"]);

  const links = [
    ["/courses", "Courses", true],
    ["/contests", "Contests", true],
    ["/dashboard", "Dashboard", !!user],
    ["/timetable", "Timetable", !!user],
    ["/practice", "Practice", !!user],
    ["/leaderboard", "Ranks", !!user],
    ["/chat", "Chat", !!user],
    ["/ai-practice", "AI Practice", !!user],
    ["/ai-assistant", "AI Tutor", !!user],
    ["/instructor/courses", "Instructor", canTeach],
    ["/admin", "Admin", canAdmin],
  ] as const;

  return (
    <header className="sticky top-0 z-40 border-b border-ink-800/90 bg-ink-950/96 backdrop-blur-xl">
      <nav className="mx-auto flex min-h-14 max-w-7xl items-center gap-2 px-3 sm:px-5 lg:px-6">
        <Link href="/" className="flex shrink-0 items-center gap-2.5 text-sm font-bold tracking-tight text-fg"><LogoMark /><span className="hidden sm:inline">SURVIVAL SCHOOL</span></Link>
        <div className="mx-auto hidden w-full max-w-sm md:block"><SearchBar /></div>
        <div className="ml-auto hidden items-center gap-0.5 lg:flex">
          {links.map(([href, label, visible]) => visible ? <Link key={href} href={href} className={navLinkClass}>{label}</Link> : null)}
        </div>
        <div className="ml-auto flex items-center gap-1.5 lg:ml-2">
          <ThemeToggle />
          {loading ? null : user ? (
            <>
              <Link href="/notifications" className="hidden rounded-lg p-2 text-fg-muted hover:bg-ink-900 hover:text-fg sm:inline-flex" aria-label="Notifications"><BellIcon /></Link>
              <Link href="/profile" className="hidden max-w-28 truncate rounded-md px-2 py-1.5 text-xs font-medium text-fg-muted hover:bg-ink-900/80 hover:text-fg lg:inline" title={user.full_name}>{user.full_name}</Link>
              <button onClick={logout} className="btn-secondary hidden !min-h-9 !px-3 !py-1.5 sm:inline-flex">Sign out</button>
            </>
          ) : (
            <><Link href="/login" className="btn-secondary hidden !min-h-9 !px-3 !py-1.5 sm:inline-flex">Sign in</Link><Link href="/register" className="btn-primary !min-h-9 !px-3 !py-1.5">Join</Link></>
          )}
          <button onClick={() => setMobileOpen((value) => !value)} className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-ink-800 bg-ink-900 text-fg-muted hover:text-fg lg:hidden" aria-label="Toggle menu" aria-expanded={mobileOpen}><MenuIcon open={mobileOpen} /></button>
        </div>
      </nav>
      {mobileOpen && (
        <div className="border-t border-ink-800 bg-ink-950 px-3 py-3 sm:px-5 lg:hidden">
          <div className="mb-3"><SearchBar /></div>
          <div className="grid grid-cols-2 gap-1 text-sm text-fg-muted">
            {links.map(([href, label, visible]) => visible ? <Link key={href} href={href} onClick={closeMobile} className={navLinkClass}>{label}</Link> : null)}
            {isPrivileged && <Link href="/notifications" onClick={closeMobile} className={navLinkClass}>Notifications</Link>}
            {user && <Link href="/profile" onClick={closeMobile} className={navLinkClass}>{user.full_name}</Link>}
            {user ? <button onClick={() => { logout(); closeMobile(); }} className="btn-secondary col-span-2 mt-1">Sign out</button> : <Link href="/login" onClick={closeMobile} className="btn-secondary col-span-2 mt-1">Sign in</Link>}
          </div>
        </div>
      )}
    </header>
  );
}

function BellIcon() { return <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} className="h-5 w-5"><path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0" /></svg>; }
function MenuIcon({ open }: { open: boolean }) { return <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} className="h-5 w-5">{open ? <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" /> : <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5M3.75 17.25h16.5" />}</svg>; }
