"use client";

import { useEffect, useRef, useState } from "react";

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
  // "unknown" covers both "not checked yet" and browsers (Safari) that
  // don't support querying this permission at all -- those fall back to
  // just trying getUserMedia() when the button is clicked, same as before.
  const [cameraPermission, setCameraPermission] = useState<"unknown" | "granted" | "denied" | "prompt">("unknown");

  // Once a browser has recorded "block" for this site's camera, NO
  // webpage's own code can make it prompt again -- that decision only the
  // user can undo, from the browser's own UI (there is no API for a site
  // to reset its own permission state; that would defeat the entire point
  // of the permission existing). What this CAN do: know the current state
  // without waiting for a failed getUserMedia() call, so a student sees
  // the real recovery instructions immediately instead of only after
  // clicking start once and getting a generic failure -- and, since
  // PermissionStatus fires a live 'change' event, notice the moment they
  // actually fix it in their browser's site settings and clear the error
  // without needing a page reload.
  const permissionStatusRef = useRef<PermissionStatus | null>(null);
  useEffect(() => {
    if (!faceProctoringRequired) return;
    if (!navigator.permissions?.query) return;
    let cancelled = false;
    navigator.permissions.query({ name: "camera" as PermissionName })
      .then((status) => {
        if (cancelled) return;
        permissionStatusRef.current = status;
        setCameraPermission(status.state as "granted" | "denied" | "prompt");
        status.onchange = () => {
          setCameraPermission(status.state as "granted" | "denied" | "prompt");
          if (status.state !== "denied") setCheckError("");
        };
      })
      .catch(() => {
        // Permissions API doesn't support querying "camera" in this
        // browser (Safari) -- cameraPermission stays "unknown", the
        // button-click getUserMedia() path below is the only check.
      });
    return () => {
      cancelled = true;
      if (permissionStatusRef.current) permissionStatusRef.current.onchange = null;
    };
  }, [faceProctoringRequired]);

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
        if (cameraPermission === "denied") {
          // Already known to be blocked -- don't bother calling
          // getUserMedia() again, it will fail identically. Send them
          // straight to the fastest fix instead of a generic error.
          setCheckError(
            "Camera is blocked for this site. Click the camera icon (or the lock/info icon) in your browser's address bar, set Camera to Allow, then click Start again — no reload needed."
          );
          if (fullscreenRequired && document.fullscreenElement) document.exitFullscreen().catch(() => {});
          setStarting(false);
          return;
        }
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
          setCheckError(
            cameraPermission === "unknown"
              ? "Camera access is required for this exam. Please allow camera permission when your browser asks, then try again."
              : "Camera is blocked for this site. Click the camera icon (or the lock/info icon) in your browser's address bar, set Camera to Allow, then click Start again — no reload needed."
          );
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
          <li className="flex gap-2">
            <span className="mt-0.5 text-red-400">✕</span>
            <span>Stay active — going untouched for a while (mouse, keyboard, or touch) counts as a violation.</span>
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
        {faceProctoringRequired && cameraPermission === "denied" && !checkError && (
          <p className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-xs text-amber-400">
            Your browser has camera access blocked for this site. Click the camera/lock icon in your address bar and set it to Allow before starting.
          </p>
        )}
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
