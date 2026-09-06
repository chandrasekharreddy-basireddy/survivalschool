"use client";

import { useEffect, useRef, useState } from "react";
import * as faceapi from "@vladmandic/face-api";

export type FaceProctorEvent = "no_face_detected" | "multiple_faces_detected";

interface Props {
  enabled: boolean;
  onProctorEvent: (event: FaceProctorEvent) => void;
  onCameraReady: () => void;
  onCameraDenied: () => void;
}

const DETECT_INTERVAL_MS = 2000;
// Consecutive missed detections before flagging "no face" -- a couple of
// bad frames (blink, brief head turn, camera hiccup) shouldn't trip a
// violation; this only fires once the face has genuinely been gone a while.
const NO_FACE_STREAK_THRESHOLD = 4; // ~8s at DETECT_INTERVAL_MS
const REPORT_COOLDOWN_MS = 15000;

let modelsLoadedPromise: Promise<void> | null = null;
function loadModels(): Promise<void> {
  if (!modelsLoadedPromise) {
    modelsLoadedPromise = faceapi.nets.tinyFaceDetector.loadFromUri("/models");
  }
  return modelsLoadedPromise;
}

type Status = "loading" | "watching" | "no_face" | "multiple_faces" | "denied" | "unsupported";

/** Runs face presence detection entirely client-side against the student's
 * own webcam feed -- no video or images ever leave the browser, only the
 * resulting violation-type events (matching how ExamIntegrityGuard already
 * reports tab/fullscreen violations), so this adds a proctoring signal
 * without adding a video-privacy liability. */
export function FaceProctor({ enabled, onProctorEvent, onCameraReady, onCameraDenied }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const noFaceStreakRef = useRef(0);
  const lastReportRef = useRef<Record<FaceProctorEvent, number>>({ no_face_detected: 0, multiple_faces_detected: 0 });
  const [status, setStatus] = useState<Status>("loading");

  const report = (event: FaceProctorEvent) => {
    const now = Date.now();
    if (now - lastReportRef.current[event] < REPORT_COOLDOWN_MS) return;
    lastReportRef.current[event] = now;
    onProctorEvent(event);
  };

  useEffect(() => {
    if (!enabled) return;
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setStatus("unsupported");
      onCameraDenied();
      return;
    }

    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | undefined;

    (async () => {
      try {
        await loadModels();
        const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 320, height: 240 } });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        setStatus("watching");
        onCameraReady();

        intervalId = setInterval(async () => {
          if (!videoRef.current || videoRef.current.readyState < 2) return;
          const detections = await faceapi.detectAllFaces(videoRef.current, new faceapi.TinyFaceDetectorOptions());
          if (detections.length === 0) {
            noFaceStreakRef.current += 1;
            if (noFaceStreakRef.current >= NO_FACE_STREAK_THRESHOLD) {
              setStatus("no_face");
              report("no_face_detected");
            }
          } else if (detections.length > 1) {
            noFaceStreakRef.current = 0;
            setStatus("multiple_faces");
            report("multiple_faces_detected");
          } else {
            noFaceStreakRef.current = 0;
            setStatus("watching");
          }
        }, DETECT_INTERVAL_MS);
      } catch {
        // NotAllowedError (denied), NotFoundError (no camera), or a model
        // fetch failure all land here -- from the exam's point of view
        // they're all "proctoring couldn't start", handled the same way.
        if (!cancelled) {
          setStatus("denied");
          onCameraDenied();
        }
      }
    })();

    return () => {
      cancelled = true;
      if (intervalId) clearInterval(intervalId);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- callbacks are expected to be stable per mount, re-running on identity churn would restart the camera
  }, [enabled]);

  if (!enabled) return null;

  const dot =
    status === "watching" ? "bg-emerald-500" :
    status === "loading" ? "bg-zinc-400 animate-pulse" :
    status === "no_face" ? "bg-amber-500" :
    "bg-red-500";
  const label =
    status === "loading" ? "Starting camera…" :
    status === "watching" ? "Face detected" :
    status === "no_face" ? "Face not visible" :
    status === "multiple_faces" ? "Multiple faces" :
    status === "denied" ? "Camera unavailable" :
    "Camera not supported";

  return (
    <div className="fixed bottom-4 right-4 z-40 w-40 overflow-hidden rounded-lg border border-ink-700 bg-bg-subtle shadow-lg">
      <video ref={videoRef} muted playsInline className="aspect-video w-full bg-black object-cover" />
      <div className="flex items-center gap-1.5 px-2 py-1.5 text-[11px] text-fg-muted">
        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
        {label}
      </div>
    </div>
  );
}
