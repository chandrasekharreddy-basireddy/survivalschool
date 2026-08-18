"use client";

import { useEffect, useRef } from "react";

/**
 * A two-part cursor: a crisp dot that tracks the pointer 1:1 and a softer ring
 * that trails with easing and swells over interactive elements. Only engages on
 * fine pointers with hover (real mice/trackpads) — touch and reduced-motion
 * visitors keep the native caret untouched. It hides the OS cursor by adding a
 * class to <html> so nothing flickers if this component ever fails to mount.
 */
export function CustomCursor() {
  const dotRef = useRef<HTMLDivElement | null>(null);
  const ringRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const fine = window.matchMedia("(hover: hover) and (pointer: fine)");
    if (!fine.matches) return;

    const dot = dotRef.current;
    const ring = ringRef.current;
    if (!dot || !ring) return;

    document.documentElement.classList.add("cursor-host", "no-native-cursor");

    let mx = window.innerWidth / 2;
    let my = window.innerHeight / 2;
    let rx = mx;
    let ry = my;
    let visible = false;
    let raf = 0;

    const onMove = (e: PointerEvent) => {
      mx = e.clientX;
      my = e.clientY;
      if (!visible) {
        visible = true;
        dot.style.opacity = "1";
        ring.style.opacity = "1";
      }
      const target = e.target as HTMLElement | null;
      const interactive = !!target?.closest(
        'a, button, [role="button"], input, textarea, select, label, summary, .card-hover'
      );
      ring.dataset.active = interactive ? "1" : "0";
    };

    const onLeave = () => {
      visible = false;
      dot.style.opacity = "0";
      ring.style.opacity = "0";
    };
    const onDown = () => (ring.dataset.press = "1");
    const onUp = () => (ring.dataset.press = "0");

    const loop = () => {
      rx += (mx - rx) * 0.18;
      ry += (my - ry) * 0.18;
      dot.style.transform = `translate3d(${mx}px, ${my}px, 0) translate(-50%, -50%)`;
      ring.style.transform = `translate3d(${rx}px, ${ry}px, 0) translate(-50%, -50%)`;
      raf = requestAnimationFrame(loop);
    };

    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("pointerdown", onDown);
    window.addEventListener("pointerup", onUp);
    document.addEventListener("pointerleave", onLeave);
    raf = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(raf);
      document.documentElement.classList.remove("cursor-host", "no-native-cursor");
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerdown", onDown);
      window.removeEventListener("pointerup", onUp);
      document.removeEventListener("pointerleave", onLeave);
    };
  }, []);

  return (
    <>
      <div
        ref={dotRef}
        aria-hidden="true"
        className="pointer-events-none fixed left-0 top-0 z-[9998] h-[6px] w-[6px] rounded-full opacity-0 transition-opacity duration-200"
        style={{ background: "rgb(var(--brand))", mixBlendMode: "normal" }}
      />
      <div
        ref={ringRef}
        aria-hidden="true"
        data-active="0"
        data-press="0"
        className="cursor-ring pointer-events-none fixed left-0 top-0 z-[9998] h-8 w-8 rounded-full opacity-0"
      />
    </>
  );
}

export default CustomCursor;
