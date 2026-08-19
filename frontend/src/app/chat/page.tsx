"use client";

import Link from "next/link";

export default function ChatEmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <p className="text-sm font-medium text-fg">Select a conversation</p>
      <p className="mt-1 text-sm text-fg-subtle">Or find someone new to message.</p>
      <Link href="/follows" className="btn-secondary mt-4">Find people</Link>
    </div>
  );
}
