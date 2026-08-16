"use client";

import { useEffect, useRef } from "react";

type IntegrityEventType = "tab_blur" | "fullscreen_exit" | "copy" | "paste" | "right_click";

interface Props {
  enabled: boolean;
  fullscreenRequired: boolean;
  onIntegrityEvent: (event: IntegrityEventType) => void;
  children: React.ReactNode;
}

const BLOCKED_KEYS = new Set(["F12", "PrintScreen"]);

export function ExamIntegrityGuard({ enabled, fullscreenRequired, onIntegrityEvent, children }: Props) {
  const lastEventRef = useRef<string>("");
  const debounceRef = useRef<number | null>(null);

  const report = (type: IntegrityEventType) => {
    const now = Date.now();
    const key = `${type}:${Math.floor(now / 500)}`;
    if (lastEventRef.current === key) return;
    lastEventRef.current = key;
    onIntegrityEvent(type);
  };

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

    return () => {
      document.removeEventListener("visibilitychange", visibility);
      document.removeEventListener("fullscreenchange", fullscreen);
      document.removeEventListener("copy", copy, true);
      document.removeEventListener("paste", paste, true);
      document.removeEventListener("cut", cut, true);
      document.removeEventListener("contextmenu", contextMenu, true);
      document.removeEventListener("keydown", keyDown, true);
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
    };
  }, [enabled, fullscreenRequired, onIntegrityEvent]);

  return <>{children}</>;
}
