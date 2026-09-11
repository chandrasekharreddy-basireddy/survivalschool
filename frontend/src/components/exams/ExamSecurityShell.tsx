"use client";

import { useState } from "react";

interface Props {
  fullscreenRequired: boolean;
  faceProctoringRequired?: boolean;
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

export function ExamSecurityShell({ fullscreenRequired, faceProctoringRequired = false, onReady, children }: Props) {
  const [accepted, setAccepted] = useState(false);
  const [starting, setStarting] = useState(false);
  const [checkError, setCheckError] = useState("");

  const handleStart = async () => {
    setStarting(true);
    setCheckError("");
    try {
      if (fullscreenRequired) {
        try {
          await document.documentElement.requestFullscreen();
        } catch {
          // Some browsers block programmatic fullscreen without a user
          // gesture in the same handler -- the check right below is what
          // actually catches that, not this catch block. Silently moving
          // on here (the old behavior) let an exam that requires
          // fullscreen start without ever actually being in it, with
          // nothing to notice until some unrelated future fullscreenchange
          // event happened to fire -- which might be never.
        }
        if (!document.fullscreenElement) {
          setCheckError("Fullscreen couldn't be enabled — your browser may have blocked it. Please allow fullscreen and try again.");
          setStarting(false);
          return;
        }
      }

      if (faceProctoringRequired) {
        try {
          // A one-time permission + device check, not continuous
          // monitoring -- the exam view's own <FaceProctor> opens its real
          // stream once the exam actually starts. This just makes sure
          // camera access is genuinely available before letting the
          // student in, rather than discovering it's missing partway
          // through the exam with no way to fix it mid-attempt.
          const stream = await navigator.mediaDevices.getUserMedia({ video: true });
          stream.getTracks().forEach((track) => track.stop());
        } catch {
          setCheckError("Camera access is required for this exam. Please allow camera permission and try again.");
          if (fullscreenRequired && document.fullscreenElement) document.exitFullscreen().catch(() => {});
          setStarting(false);
          return;
        }
      }

      const fp = getDeviceFingerprint();
      setAccepted(true);
      onReady(fp);
    } finally {
      setStarting(false);
    }
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
          {faceProctoringRequired && (
            <li className="flex gap-2">
              <span className="mt-0.5 text-red-400">✕</span>
              <span>Stay visible to your camera the whole time. Losing face detection counts as a violation.</span>
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
        {checkError && (
          <p className="mt-4 rounded-lg border border-red-500/40 bg-red-500/5 px-3 py-2 text-xs text-red-400">{checkError}</p>
        )}
        <button type="button" onClick={handleStart} disabled={starting} className="btn-primary mt-6 w-full disabled:opacity-60">
          {starting ? "Checking…" : "I understand — start exam"}
        </button>
      </div>
    </div>
  );
}
