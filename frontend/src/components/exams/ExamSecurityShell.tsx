"use client";

import { useState } from "react";

interface Props {
  fullscreenRequired: boolean;
  onReady: (fingerprint: string) => void;
  children: React.ReactNode;
}

function getDeviceFingerprint(): string {
  const parts = [
    navigator.userAgent,
    `${screen.width}x${screen.height}`,
    Intl.DateTimeFormat().resolvedOptions().timeZone,
    navigator.language,
  ];
  let hash = 0;
  const str = parts.join("|");
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash + str.charCodeAt(i)) | 0;
  }
  return Math.abs(hash).toString(36);
}

export function ExamSecurityShell({ fullscreenRequired, onReady, children }: Props) {
  const [accepted, setAccepted] = useState(false);

  const handleStart = async () => {
    if (fullscreenRequired) {
      try {
        await document.documentElement.requestFullscreen();
      } catch {
        // Some browsers block programmatic fullscreen without user gesture in the same handler
      }
    }
    const fp = getDeviceFingerprint();
    setAccepted(true);
    onReady(fp);
  };

  if (accepted) return <>{children}</>;

  return (
    <div className="flex min-h-screen items-center justify-center bg-ink-950 px-4">
      <div className="max-w-lg rounded-xl border border-ink-700 bg-ink-900 p-8 text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-brand-500/10 text-2xl">
          🔒
        </div>
        <h2 className="text-xl font-bold text-fg">Exam Security Rules</h2>
        <ul className="mt-5 space-y-3 text-left text-sm text-fg-muted">
          <li className="flex gap-2">
            <span className="mt-0.5 text-red-400">✕</span>
            <span>Do not switch tabs or leave this window during the exam.</span>
          </li>
          {fullscreenRequired && (
            <li className="flex gap-2">
              <span className="mt-0.5 text-red-400">✕</span>
              <span>Do not exit fullscreen mode. The exam requires fullscreen.</span>
            </li>
          )}
          <li className="flex gap-2">
            <span className="mt-0.5 text-red-400">✕</span>
            <span>Copy, paste, and right-click are disabled.</span>
          </li>
          <li className="flex gap-2">
            <span className="mt-0.5 text-red-400">✕</span>
            <span>Changing your device mid-exam will immediately terminate the session.</span>
          </li>
          <li className="flex gap-2">
            <span className="mt-0.5 text-amber-400">⚠</span>
            <span>You will receive <strong className="text-fg">2 warnings</strong> before your exam is terminated.</span>
          </li>
        </ul>
        <button type="button" onClick={handleStart} className="btn-primary mt-6 w-full">
          I understand — start exam
        </button>
      </div>
    </div>
  );
}
