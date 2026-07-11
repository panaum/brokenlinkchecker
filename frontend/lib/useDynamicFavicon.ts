"use client";

import { useEffect, useRef } from "react";

export type FaviconState = "idle" | "scanning" | "healthy" | "issues";

const SIGNAL = "#a855f7";   // accent (scanning / idle)
const GREEN = "#34d399";    // health (healthy)
const RED = "#f87171";      // health (issues)
const INK = "#14131c";

function draw(ctx: CanvasRenderingContext2D, state: FaviconState, phase: number) {
  const S = 32;
  ctx.clearRect(0, 0, S, S);
  // Rounded dark tile.
  ctx.fillStyle = INK;
  ctx.beginPath();
  ctx.roundRect(0, 0, S, S, 7);
  ctx.fill();

  const cx = S / 2, cy = S / 2;
  if (state === "scanning") {
    // Rotating radar arc.
    ctx.strokeStyle = "rgba(168,85,247,0.25)";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(cx, cy, 10, 0, Math.PI * 2);
    ctx.stroke();
    ctx.strokeStyle = SIGNAL;
    ctx.beginPath();
    ctx.arc(cx, cy, 10, phase, phase + Math.PI / 2);
    ctx.stroke();
  } else if (state === "healthy") {
    // Green ring + center dot.
    ctx.strokeStyle = GREEN;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(cx, cy, 10, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = GREEN;
    ctx.beginPath();
    ctx.arc(cx, cy, 3.5, 0, Math.PI * 2);
    ctx.fill();
  } else if (state === "issues") {
    // Red alert dot.
    ctx.fillStyle = RED;
    ctx.beginPath();
    ctx.arc(cx, cy, 8, 0, Math.PI * 2);
    ctx.fill();
  } else {
    // Idle — quiet teal dot.
    ctx.fillStyle = SIGNAL;
    ctx.beginPath();
    ctx.arc(cx, cy, 6, 0, Math.PI * 2);
    ctx.fill();
  }
}

function setFavicon(dataUrl: string) {
  let link = document.querySelector<HTMLLinkElement>("link#dynamic-favicon");
  if (!link) {
    link = document.createElement("link");
    link.id = "dynamic-favicon";
    link.rel = "icon";
    document.head.appendChild(link);
  }
  link.href = dataUrl;
}

/**
 * Reflect scan state in the tab favicon: a rotating radar during a scan, a
 * green ring when healthy, a red dot when the last scan found issues. Respects
 * prefers-reduced-motion (no rotation — a static arc).
 */
export function useDynamicFavicon(state: FaviconState) {
  const rafRef = useRef<number | null>(null);
  const phaseRef = useRef(0);

  useEffect(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 32;
    canvas.height = 32;
    const ctx = canvas.getContext("2d");
    if (!ctx || typeof ctx.roundRect !== "function") return;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (state === "scanning" && !reduce) {
      const tick = () => {
        phaseRef.current += 0.18;
        draw(ctx, state, phaseRef.current);
        setFavicon(canvas.toDataURL("image/png"));
        rafRef.current = requestAnimationFrame(tick);
      };
      rafRef.current = requestAnimationFrame(tick);
      return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
    }

    draw(ctx, state, phaseRef.current);
    setFavicon(canvas.toDataURL("image/png"));
  }, [state]);
}
