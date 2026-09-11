"use client";

import { useEffect, useState } from "react";

/** Tracks document.fullscreenElement so the app's own chrome (NavBar,
 * Footer) can hide itself while a locked-down exam is active in fullscreen
 * -- every exam type (contests, elimination battles, classroom exams)
 * already calls document.documentElement.requestFullscreen() the same way,
 * so this one hook covers all of them without any exam page needing to
 * know about NavBar/Footer, and without NavBar/Footer needing to know
 * which route it is. */
export function useIsFullscreen(): boolean {
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    const update = () => setIsFullscreen(!!document.fullscreenElement);
    update();
    document.addEventListener("fullscreenchange", update);
    return () => document.removeEventListener("fullscreenchange", update);
  }, []);

  return isFullscreen;
}
