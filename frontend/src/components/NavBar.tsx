"use client";

import Link from "next/link";
import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { ThemeToggle } from "@/components/ThemeToggle";
import { SearchBar } from "@/components/SearchBar";

const navLinkClass = "rounded-md px-2 py-1.5 transition-colors hover:bg-ink-900/70 hover:text-fg";

export function NavBar() {
  const { user, loading, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-ink-800/90 bg-ink-950/95 backdrop-blur">
      <nav className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-3 py-2.5 sm:px-5">
        <Link href="/" className="flex shrink-0 items-center gap-2 text-base font-semibold tracking-tight text-fg">
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-ink-700 bg-ink-900">
            <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" aria-hidden="true">
              <path d="M4 10.5 12 6l8 4.5-8 4.5-8-4.5Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
              <path d="M7 13.5V16c0 1.4 2.2 2.8 5 2.8s5-1.4 5-2.8v-2.5M20 10.5v5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <span className="hidden sm:inline">Survival School</span>
        </Link>

        <div className="hidden max-w-xs flex-1 md:block">
          <SearchBar />
        </div>

        <div className="hidden items-center gap-1 text-sm text-fg-muted lg:flex">
          <Link href="/courses" className={navLinkClass}>Courses</Link>
          <Link href="/contests" className={navLinkClass}>Contests</Link>
          {user && <Link href="/dashboard" className={navLinkClass}>Dashboard</Link>}
          {user && <Link href="/timetable" className={navLinkClass}>Timetable</Link>}
          {user && <Link href="/practice" className={navLinkClass}>Practice</Link>}
          {user && <Link href="/leaderboard" className={navLinkClass}>Leaderboard</Link>}
          {user && <Link href="/chat" className={navLinkClass}>Chat</Link>}
          {user && <Link href="/ai-practice" className={navLinkClass}>AI Practice</Link>}
          {user && <Link href="/ai-assistant" className={navLinkClass}>AI Tutor</Link>}
          {user?.roles.some((r) => ["INSTRUCTOR", "ADMIN", "SUPER_ADMIN"].includes(r)) && <Link href="/instructor/courses" className={navLinkClass}>Instructor</Link>}
          {user?.roles.some((r) => ["ADMIN", "SUPER_ADMIN"].includes(r)) && <Link href="/admin" className={navLinkClass}>Admin</Link>}
        </div>

        <div className="flex items-center gap-2">
          <ThemeToggle />
          {loading ? null : user ? (
            <>
              <Link href="/notifications" className="hidden rounded-md p-2 text-fg-muted hover:bg-ink-900/70 hover:text-fg sm:inline-flex" aria-label="Notifications"><BellIcon /></Link>
              <Link href="/profile" className="hidden max-w-32 truncate rounded-md px-2 py-1.5 text-sm text-fg-muted hover:bg-ink-900/70 hover:text-fg lg:inline" title={user.full_name}>{user.full_name}</Link>
              <button onClick={() => logout()} className="btn-secondary hidden !min-h-9 !px-3 !py-1.5 sm:inline-flex">Sign out</button>
            </>
          ) : (
            <>
              <Link href="/login" className="btn-secondary hidden !min-h-9 !px-3 !py-1.5 sm:inline-flex">Sign in</Link>
              <Link href="/register" className="btn-primary !min-h-9 !px-3 !py-1.5">Get started</Link>
            </>
          )}
          <button onClick={() => setMobileOpen((v) => !v)} className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-fg-muted hover:bg-ink-900 hover:text-fg lg:hidden" aria-label="Toggle menu" aria-expanded={mobileOpen}>
            <MenuIcon open={mobileOpen} />
          </button>
        </div>
      </nav>

      {mobileOpen && (
        <div className="border-t border-ink-800 px-3 py-3 sm:px-5 lg:hidden">
          <div className="mb-3 md:hidden"><SearchBar /></div>
          <div className="flex flex-col gap-1 text-sm text-fg-muted">
            <Link href="/courses" onClick={() => setMobileOpen(false)} className={navLinkClass}>Courses</Link>
            <Link href="/contests" onClick={() => setMobileOpen(false)} className={navLinkClass}>Contests</Link>
            {user && <Link href="/dashboard" onClick={() => setMobileOpen(false)} className={navLinkClass}>Dashboard</Link>}
            {user && <Link href="/timetable" onClick={() => setMobileOpen(false)} className={navLinkClass}>Timetable</Link>}
            {user && <Link href="/practice" onClick={() => setMobileOpen(false)} className={navLinkClass}>Practice</Link>}
            {user && <Link href="/leaderboard" onClick={() => setMobileOpen(false)} className={navLinkClass}>Leaderboard</Link>}
            {user && <Link href="/chat" onClick={() => setMobileOpen(false)} className={navLinkClass}>Chat</Link>}
            {user && <Link href="/ai-practice" onClick={() => setMobileOpen(false)} className={navLinkClass}>AI Practice</Link>}
            {user && <Link href="/ai-assistant" onClick={() => setMobileOpen(false)} className={navLinkClass}>AI Tutor</Link>}
            {user?.roles.some((r) => ["INSTRUCTOR", "ADMIN", "SUPER_ADMIN"].includes(r)) && <Link href="/instructor/courses" onClick={() => setMobileOpen(false)} className={navLinkClass}>Instructor</Link>}
            {user?.roles.some((r) => ["ADMIN", "SUPER_ADMIN"].includes(r)) && <Link href="/admin" onClick={() => setMobileOpen(false)} className={navLinkClass}>Admin</Link>}
            {user ? (
              <>
                <Link href="/profile" onClick={() => setMobileOpen(false)} className={navLinkClass}>{user.full_name}</Link>
                <button onClick={() => logout()} className="btn-secondary mt-1 justify-center">Sign out</button>
              </>
            ) : <Link href="/login" onClick={() => setMobileOpen(false)} className="btn-secondary mt-1 justify-center">Sign in</Link>}
          </div>
        </div>
      )}
    </header>
  );
}

function BellIcon() {
  return <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} className="h-5 w-5"><path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0" /></svg>;
}

function MenuIcon({ open }: { open: boolean }) {
  return <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} className="h-5 w-5">{open ? <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" /> : <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5M3.75 17.25h16.5" />}</svg>;
}
