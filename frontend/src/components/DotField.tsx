"use client";

import { useEffect, useRef } from "react";

/**
 * Signature background: a fixed grid of dots that behaves like a gravity well
 * around the pointer. Dots near the cursor are pushed outward and lit toward
 * the accent colour, then ease back home when it leaves — the "antigravity"
 * feel. It reads its colours from the live CSS variables so it tracks the
 * light/dark theme, watches <html> for the theme class flipping, pauses when
 * the tab is hidden, and degrades to a calm static grid when the visitor
 * prefers reduced motion or is on a coarse (touch) pointer.
 */
export function DotField() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return;

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

    const SPACING = 34;
    const DOT_R = 1.15;
    const INFLUENCE = 150;
    const PUSH = 26;

    let dpr = Math.min(window.devicePixelRatio || 1, 2);
    let width = 0;
    let height = 0;
    let cols = 0;
    let rows = 0;

    type Dot = { hx: number; hy: number; x: number; y: number };
    let dots: Dot[] = [];

    // Colours pulled from the theme; refreshed when the theme flips.
    let baseColor = "148 163 184";
    let litColor = "255 96 116";
    const readColors = () => {
      const s = getComputedStyle(document.documentElement);
      baseColor = s.getPropertyValue("--dot").trim() || baseColor;
      litColor = s.getPropertyValue("--dot-lit").trim() || litColor;
    };

    const build = () => {
      width = canvas.clientWidth;
      height = canvas.clientHeight;
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      cols = Math.ceil(width / SPACING) + 1;
      rows = Math.ceil(height / SPACING) + 1;
      dots = [];
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const hx = c * SPACING;
          const hy = r * SPACING;
          dots.push({ hx, hy, x: hx, y: hy });
        }
      }
    };

    const pointer = { x: -9999, y: -9999, active: false };

    const drawStatic = () => {
      ctx.clearRect(0, 0, width, height);
      for (const d of dots) {
        ctx.beginPath();
        ctx.arc(d.hx, d.hy, DOT_R, 0, Math.PI * 2);
        ctx.fillStyle = `rgb(${baseColor} / 0.18)`;
        ctx.fill();
      }
    };

    let raf = 0;
    const frame = () => {
      ctx.clearRect(0, 0, width, height);
      const inf2 = INFLUENCE * INFLUENCE;
      for (const d of dots) {
        let tx = d.hx;
        let ty = d.hy;
        let lit = 0;
        if (pointer.active) {
          const dx = d.hx - pointer.x;
          const dy = d.hy - pointer.y;
          const dist2 = dx * dx + dy * dy;
          if (dist2 < inf2) {
            const dist = Math.sqrt(dist2) || 1;
            const force = 1 - dist / INFLUENCE; // 1 at centre → 0 at edge
            const push = force * PUSH;
            tx = d.hx + (dx / dist) * push;
            ty = d.hy + (dy / dist) * push;
            lit = force;
          }
        }
        // Ease toward the target for a springy settle.
        d.x += (tx - d.x) * 0.14;
        d.y += (ty - d.y) * 0.14;

        const r = DOT_R + lit * 1.7;
        const baseAlpha = 0.16 + lit * 0.5;
        ctx.beginPath();
        ctx.arc(d.x, d.y, r, 0, Math.PI * 2);
        if (lit > 0.02) {
          ctx.fillStyle = `rgb(${litColor} / ${Math.min(baseAlpha + 0.15, 0.95)})`;
        } else {
          ctx.fillStyle = `rgb(${baseColor} / ${baseAlpha})`;
        }
        ctx.fill();
      }
      raf = requestAnimationFrame(frame);
    };

    const start = () => {
      if (raf) return;
      raf = requestAnimationFrame(frame);
    };
    const stop = () => {
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
    };

    const onMove = (e: PointerEvent) => {
      pointer.x = e.clientX;
      pointer.y = e.clientY;
      pointer.active = true;
    };
    const onLeave = () => {
      pointer.active = false;
    };
    const onVisibility = () => {
      if (document.hidden) stop();
      else if (!reduceMotion && finePointer) start();
    };
    const themeObserver = new MutationObserver(() => readColors());

    readColors();
    build();
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });

    let resizeTimer = 0;
    const onResize = () => {
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(() => {
        build();
        if (reduceMotion || !finePointer) drawStatic();
      }, 150);
    };
    window.addEventListener("resize", onResize);

    if (reduceMotion || !finePointer) {
      drawStatic();
    } else {
      window.addEventListener("pointermove", onMove, { passive: true });
      window.addEventListener("pointerdown", onMove, { passive: true });
      document.addEventListener("pointerleave", onLeave);
      document.addEventListener("visibilitychange", onVisibility);
      start();
    }

    return () => {
      stop();
      themeObserver.disconnect();
      window.removeEventListener("resize", onResize);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerdown", onMove);
      document.removeEventListener("pointerleave", onLeave);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 -z-10 h-full w-full"
    />
  );
}

export default DotField;
