"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { WarningModal } from "./WarningModal";

type IntegrityEventType = "tab_blur" | "fullscreen_exit" | "copy" | "paste" | "right_click";

interface Props {
  enabled: boolean;
  fullscreenRequired: boolean;
  maxWarnings?: number;
  onIntegrityEvent: (event: IntegrityEventType) => void;
  onTerminate?: () => void;
  children: React.ReactNode;
}

const BLOCKED_KEYS = new Set(["F12", "PrintScreen"]);

export function ExamIntegrityGuard({ enabled, fullscreenRequired, maxWarnings = 2, onIntegrityEvent, onTerminate, children }: Props) {
  const lastEventRef = useRef<string>("");
  const [warningCount, setWarningCount] = useState(0);
  const [pendingWarning, setPendingWarning] = useState<{ number: number; reason: string } | null>(null);

  const report = useCallback((type: IntegrityEventType) => {
    const now = Date.now();
    const key = `${type}:${Math.floor(now / 500)}`;
    if (lastEventRef.current === key) return;
    lastEventRef.current = key;
    onIntegrityEvent(type);

    setWarningCount(prev => {
      const next = prev + 1;
      if (next <= maxWarnings) {
        setPendingWarning({ number: next, reason: type });
      } else {
        onTerminate?.();
      }
      return next;
    });
  }, [maxWarnings, onIntegrityEvent, onTerminate]);

  const handleAcknowledge = useCallback(() => {
    setPendingWarning(null);
    if (fullscreenRequired && !document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
    }
  }, [fullscreenRequired]);

  useEffect(() => {
    if (!enabled) return;

    const visibility = () => {
      if (document.hidden) report("tab_blur");
    };
    const fullscreen = () => {
      if (fullscreenRequired && !document.fullscreenElement) report("fullscreen_exit");
    };
    const copy = (event: ClipboardEvent) => {
      event.preventDefault();
      report("copy");
    };
    const paste = (event: ClipboardEvent) => {
      event.preventDefault();
      report("paste");
    };
    const cut = (event: ClipboardEvent) => {
      event.preventDefault();
      report("copy");
    };
    const contextMenu = (event: MouseEvent) => {
      event.preventDefault();
      report("right_click");
    };
    const keyDown = (event: KeyboardEvent) => {
      const key = event.key;
      const blockedCombo =
        (event.ctrlKey || event.metaKey) && ["c", "v", "x", "s", "p", "u"].includes(key.toLowerCase());
      const blockedDevTools = (event.ctrlKey || event.metaKey) && event.shiftKey && ["i", "j", "c"].includes(key.toLowerCase());
      if (BLOCKED_KEYS.has(key) || blockedCombo || blockedDevTools || key === "F5") {
        event.preventDefault();
        event.stopPropagation();
        report(key === "PrintScreen" ? "copy" : "right_click");
      }
    };

    document.addEventListener("visibilitychange", visibility);
    document.addEventListener("fullscreenchange", fullscreen);
    document.addEventListener("copy", copy, true);
    document.addEventListener("paste", paste, true);
    document.addEventListener("cut", cut, true);
    document.addEventListener("contextmenu", contextMenu, true);
    document.addEventListener("keydown", keyDown, true);

    // Verify the CURRENT state the instant monitoring turns on, not just
    // subsequent changes. Both listeners above only fire on a *transition*
    // (fullscreenchange, visibilitychange) -- if fullscreen was never
    // actually entered (the request silently failed, lost its user-gesture
    // context, or an exam was resumed some other way) there is no future
    // transition to ever catch it, so the exam would run with zero
    // enforcement the entire time and nothing would ever look wrong here.
    // Checking once, right now, closes that gap.
    fullscreen();
    visibility();

    return () => {
      document.removeEventListener("visibilitychange", visibility);
      document.removeEventListener("fullscreenchange", fullscreen);
      document.removeEventListener("copy", copy, true);
      document.removeEventListener("paste", paste, true);
      document.removeEventListener("cut", cut, true);
      document.removeEventListener("contextmenu", contextMenu, true);
      document.removeEventListener("keydown", keyDown, true);
    };
  }, [enabled, fullscreenRequired, report]);

  return (
    <>
      {children}
      {pendingWarning && (
        <WarningModal
          warningNumber={pendingWarning.number}
          maxWarnings={maxWarnings}
          reason={pendingWarning.reason}
          onAcknowledge={handleAcknowledge}
        />
      )}
    </>
  );
}
