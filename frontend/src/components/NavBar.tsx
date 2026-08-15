"use client";

import Link from "next/link";
import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { ThemeToggle } from "@/components/ThemeToggle";
import { SearchBar } from "@/components/SearchBar";

export function NavBar() {
  const { user, loading, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-ink-800 bg-ink-950/80 backdrop-blur">
      <nav className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-4 sm:px-6">
        <Link href="/" className="flex shrink-0 items-center gap-2 text-lg font-bold tracking-tight text-fg">
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-brand-700 bg-ink-950">
            <svg viewBox="0 0 32 32" fill="none" className="h-5 w-5" aria-hidden="true">
              <circle cx="16" cy="9.5" r="3.1" stroke="#ff3b3f" strokeWidth="2.2" />
              <path d="M9.6 22.8 L14 15 L18.4 22.8 Z" stroke="#ff3b3f" strokeWidth="2.2" strokeLinejoin="round" />
              <rect x="18.6" y="17.3" width="6.4" height="6.4" stroke="#ff3b3f" strokeWidth="2.2" />
            </svg>
          </span>
          <span className="hidden sm:inline">Survival School</span>
        </Link>

        <div className="hidden max-w-xs flex-1 md:block">
          <SearchBar />
        </div>

        <div className="hidden items-center gap-6 text-sm text-fg-muted lg:flex">
          <Link href="/courses" className="hover:text-fg">Courses</Link>
          <Link href="/contests" className="hover:text-fg">Contests</Link>
          {user && <Link href="/dashboard" className="hover:text-fg">Dashboard</Link>}
          {user && <Link href="/timetable" className="hover:text-fg">Timetable</Link>}
          {user && <Link href="/daily-challenge" className="hover:text-fg">Daily Challenge</Link>}
          {user && <Link href="/practice" className="hover:text-fg">Practice</Link>}
          {user && <Link href="/ai-practice" className="hover:text-fg">AI Practice</Link>}
          {user && <Link href="/leaderboard" className="hover:text-fg">Leaderboard</Link>}
          {user && <Link href="/chat" className="hover:text-fg">Chat</Link>}
          {user && <Link href="/ai-assistant" className="hover:text-fg">AI Tutor</Link>}
          {user?.roles.some((r) => ["INSTRUCTOR", "ADMIN", "SUPER_ADMIN"].includes(r)) && (
            <Link href="/instructor/courses" className="hover:text-fg">Instructor</Link>
          )}
          {user?.roles.some((r) => ["ADMIN", "SUPER_ADMIN"].includes(r)) && (
            <Link href="/admin" className="hover:text-fg">Admin</Link>
          )}
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
          <ThemeToggle />
          {loading ? null : user ? (
            <>
              <Link href="/notifications" className="hidden text-fg-muted hover:text-fg sm:inline" aria-label="Notifications">
                <BellIcon />
              </Link>
              <Link href="/profile" className="hidden text-sm text-fg-muted hover:text-fg lg:inline">{user.full_name}</Link>
              <button onClick={() => logout()} className="btn-secondary hidden !px-4 !py-2 sm:inline-flex">
                Sign out
              </button>
            </>
          ) : (
            <>
              <Link href="/login" className="btn-secondary hidden !px-4 !py-2 sm:inline-flex">Sign in</Link>
              <Link href="/register" className="btn-primary !px-4 !py-2">Get started</Link>
            </>
          )}
          <button
            onClick={() => setMobileOpen((v) => !v)}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-fg-muted hover:bg-ink-900 hover:text-fg lg:hidden"
            aria-label="Toggle menu"
            aria-expanded={mobileOpen}
          >
            <MenuIcon open={mobileOpen} />
          </button>
        </div>
      </nav>

      {mobileOpen && (
        <div className="border-t border-ink-800 px-4 py-4 lg:hidden">
          <div className="mb-4 md:hidden">
            <SearchBar />
          </div>
          <div className="flex flex-col gap-3 text-sm text-fg-muted">
            <Link href="/courses" onClick={() => setMobileOpen(false)} className="hover:text-fg">Courses</Link>
            <Link href="/contests" onClick={() => setMobileOpen(false)} className="hover:text-fg">Contests</Link>
            {user && <Link href="/dashboard" onClick={() => setMobileOpen(false)} className="hover:text-fg">Dashboard</Link>}
            {user && <Link href="/timetable" onClick={() => setMobileOpen(false)} className="hover:text-fg">Timetable</Link>}
            {user && <Link href="/daily-challenge" onClick={() => setMobileOpen(false)} className="hover:text-fg">Daily Challenge</Link>}
            {user && <Link href="/practice" onClick={() => setMobileOpen(false)} className="hover:text-fg">Practice</Link>}
            {user && <Link href="/ai-practice" onClick={() => setMobileOpen(false)} className="hover:text-fg">AI Practice</Link>}
            {user && <Link href="/leaderboard" onClick={() => setMobileOpen(false)} className="hover:text-fg">Leaderboard</Link>}
            {user && <Link href="/chat" onClick={() => setMobileOpen(false)} className="hover:text-fg">Chat</Link>}
            {user && <Link href="/ai-assistant" onClick={() => setMobileOpen(false)} className="hover:text-fg">AI Tutor</Link>}
            {user?.roles.some((r) => ["INSTRUCTOR", "ADMIN", "SUPER_ADMIN"].includes(r)) && (
              <Link href="/instructor/courses" onClick={() => setMobileOpen(false)} className="hover:text-fg">Instructor</Link>
            )}
            {user?.roles.some((r) => ["ADMIN", "SUPER_ADMIN"].includes(r)) && (
              <Link href="/admin" onClick={() => setMobileOpen(false)} className="hover:text-fg">Admin</Link>
            )}
            {user ? (
              <>
                <Link href="/profile" onClick={() => setMobileOpen(false)} className="hover:text-fg">{user.full_name}</Link>
                <button onClick={() => logout()} className="btn-secondary mt-2 justify-center">Sign out</button>
              </>
            ) : (
              <Link href="/login" onClick={() => setMobileOpen(false)} className="btn-secondary mt-2 justify-center">Sign in</Link>
            )}
          </div>
        </div>
      )}
    </header>
  );
}

function BellIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} className="h-5 w-5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0" />
    </svg>
  );
}

function MenuIcon({ open }: { open: boolean }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} className="h-5 w-5">
      {open ? (
        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
      ) : (
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5M3.75 17.25h16.5" />
      )}
    </svg>
  );
}
