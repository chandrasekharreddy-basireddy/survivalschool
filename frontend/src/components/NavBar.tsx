"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth-context";

export function NavBar() {
  const { user, loading, logout } = useAuth();

  return (
    <header className="sticky top-0 z-40 border-b border-ink-800 bg-ink-950/80 backdrop-blur">
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2 text-lg font-bold tracking-tight text-white">
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-brand-400 to-purple-500 text-sm">
            SS
          </span>
          Survival School
        </Link>

        <div className="hidden items-center gap-6 text-sm text-slate-300 sm:flex">
          <Link href="/courses" className="hover:text-white">Courses</Link>
          {user && <Link href="/dashboard" className="hover:text-white">Dashboard</Link>}
          {user && <Link href="/leaderboard" className="hover:text-white">Leaderboard</Link>}
          {user && <Link href="/chat" className="hover:text-white">Chat</Link>}
          {user && <Link href="/ai-assistant" className="hover:text-white">AI Tutor</Link>}
          {user?.roles.some((r) => ["INSTRUCTOR", "ADMIN", "SUPER_ADMIN"].includes(r)) && (
            <Link href="/instructor/courses" className="hover:text-white">Instructor</Link>
          )}
          {user?.roles.some((r) => ["ADMIN", "SUPER_ADMIN"].includes(r)) && (
            <Link href="/admin" className="hover:text-white">Admin</Link>
          )}
        </div>

        <div className="flex items-center gap-3">
          {loading ? null : user ? (
            <>
              <Link href="/notifications" className="hidden text-slate-400 hover:text-white sm:inline" aria-label="Notifications">
                <BellIcon />
              </Link>
              <Link href="/profile" className="hidden text-sm text-slate-400 hover:text-white sm:inline">{user.full_name}</Link>
              <button onClick={() => logout()} className="btn-secondary !px-4 !py-2">
                Sign out
              </button>
            </>
          ) : (
            <>
              <Link href="/login" className="btn-secondary !px-4 !py-2">Sign in</Link>
              <Link href="/register" className="btn-primary !px-4 !py-2">Get started</Link>
            </>
          )}
        </div>
      </nav>
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
