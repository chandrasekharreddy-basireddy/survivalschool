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
          {user?.roles.some((r) => ["ADMIN", "SUPER_ADMIN"].includes(r)) && (
            <Link href="/admin" className="hover:text-white">Admin</Link>
          )}
        </div>

        <div className="flex items-center gap-3">
          {loading ? null : user ? (
            <>
              <span className="hidden text-sm text-slate-400 sm:inline">{user.full_name}</span>
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
