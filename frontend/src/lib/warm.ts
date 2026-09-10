/** Fires the earliest possible request to the backend, before any React
 * component mounts or hydrates — injected as a raw <head> script the same
 * way NO_FLASH_THEME_SCRIPT is (see src/lib/theme.tsx). The backend runs on
 * Render's free tier, which sleeps after ~15 minutes idle and takes 15-50s
 * to wake on the next request; every page's own data-fetching effects (e.g.
 * ContestsPage's /contests/upcoming call) would otherwise be the request
 * that wakes it, forcing the user to sit through the full cold start with
 * nothing but a bare "Loading…" state. Pinging /health this early — before
 * the JS bundle even finishes executing — gives the backend a genuine head
 * start, so real data requests land against a backend that is already
 * waking up (or awake) rather than one that is stone cold. Best-effort and
 * fire-and-forget: a failure here must never surface to the user, since its
 * only job is to shave time off a request someone else will make anyway. */
export const WARM_BACKEND_SCRIPT = `
(function () {
  try {
    var base = ${JSON.stringify(process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1")};
    fetch(base + '/health', { method: 'GET', mode: 'cors', keepalive: true, cache: 'no-store' }).catch(function () {});
  } catch (e) {}
})();
`;
