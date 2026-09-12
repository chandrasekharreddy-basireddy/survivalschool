"use client";

import { useEffect, useState } from "react";

// A page-level pub/sub, not React context: Sidebar/Footer are rendered once
// in the root layout, far above any specific exam page, and plumbing a
// context provider down to them (or wrapping the whole app in one just for
// this) is a lot of surface area for "hide two components while true".
const EXAM_MODE_EVENT = "survivalschool:exam-chrome-change";
let examModeActive = false;

/** Called by an exam-taking page (classroom exam, contest, elimination
 * battle) to hide the site header/footer for as long as the exam is
 * actually running -- deliberately independent of whether the Fullscreen
 * API happens to be engaged. Fullscreen can fail to actually activate for
 * reasons outside this app's control (browser policy, a blocked
 * permission, a lost user-gesture context); when that happens the exam is
 * still genuinely in progress and the site chrome hiding itself is still
 * exactly as important -- more so, since it's also the easiest way out of
 * a locked-down exam back to the rest of the site. */
export function setExamChromeHidden(active: boolean): void {
  if (examModeActive === active) return;
  examModeActive = active;
  if (typeof window !== "undefined") window.dispatchEvent(new Event(EXAM_MODE_EVENT));
}

/** True while either the browser is actually in fullscreen OR an exam page
 * has called setExamChromeHidden(true) -- used by Sidebar/Footer to hide
 * themselves. */
export function useHideChrome(): boolean {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [examMode, setExamMode] = useState(examModeActive);

  useEffect(() => {
    const updateFullscreen = () => setIsFullscreen(!!document.fullscreenElement);
    updateFullscreen();
    document.addEventListener("fullscreenchange", updateFullscreen);

    const updateExamMode = () => setExamMode(examModeActive);
    updateExamMode();
    window.addEventListener(EXAM_MODE_EVENT, updateExamMode);

    return () => {
      document.removeEventListener("fullscreenchange", updateFullscreen);
      window.removeEventListener(EXAM_MODE_EVENT, updateExamMode);
    };
  }, []);

  return isFullscreen || examMode;
}
