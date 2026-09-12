/**
 * Camera-based face proctoring was disabled for one specific presentation
 * night after live camera-permission failures (browser site permission vs.
 * OS-level privacy settings, camera-in-use conflicts). The underlying check
 * (ExamSecurityShell) was hardened the same night: it now always re-verifies
 * via a real getUserMedia() call instead of a cached permission read, and
 * gives a precise reason (blocked / in-use / no camera) instead of one
 * generic error. Re-enabled now that the deliberate presentation-day
 * disable is no longer needed -- the residual risk (a student's own browser
 * or OS blocking camera access) is a real, unavoidable limitation, not a
 * bug in this code, and is already surfaced with clear recovery
 * instructions when it happens.
 */
export const FACE_PROCTORING_ENABLED = true;
