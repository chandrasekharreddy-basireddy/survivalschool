"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";

interface Battle { id: string }

// The join lock is short-held (a single DB insert) and non-blocking, so
// under a burst of simultaneous joiners (many people scanning the same QR
// code at once — exactly what this page exists for) most attempts land on
// "being updated, try again" rather than queuing. A few quick retries clear
// almost all of them without the player having to do anything.
const RETRY_DELAYS_MS = [400, 900, 1600];

function isRetryableConflict(err: unknown): boolean {
  return err instanceof ApiError && err.status === 409;
}

/** The landing target for a shared room code or a scanned QR — auto-joins
 * the battle and drops the player straight into the lobby, matching the
 * "custom match, join by room id" flow the code/QR was built for. */
export default function JoinBattlePage() {
  const params = useParams<{ code: string }>();
  const router = useRouter();
  const { user, loading } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const attempted = useRef(false);

  const attemptJoin = async () => {
    for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt++) {
      try {
        const battle = await apiFetch<Battle>("/elimination/battles/join", { method: "POST", body: JSON.stringify({ code: params.code }) });
        router.replace(`/elimination/${battle.id}`);
        return;
      } catch (err) {
        const isLastAttempt = attempt === RETRY_DELAYS_MS.length;
        if (!isRetryableConflict(err) || isLastAttempt) {
          setError(err instanceof ApiError ? err.message : "Couldn't join that battle.");
          setRetrying(false);
          return;
        }
        setRetrying(true);
        await new Promise((resolve) => setTimeout(resolve, RETRY_DELAYS_MS[attempt]));
      }
    }
  };

  useEffect(() => {
    if (loading) return;
    if (!user) {
      const next = encodeURIComponent(`/elimination/join/${params.code}`);
      router.replace(`/login?next=${next}`);
      return;
    }
    if (attempted.current) return;
    attempted.current = true;
    void attemptJoin();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, loading, params.code, router]);

  const retryManually = () => {
    setError(null);
    void attemptJoin();
  };

  return (
    <div className="mx-auto max-w-md px-6 py-24 text-center">
      {error ? (
        <>
          <p className="text-fg">{error}</p>
          <div className="mt-6 flex justify-center gap-3">
            <button type="button" onClick={retryManually} className="btn-primary">Try again</button>
            <Link href="/elimination" className="btn-secondary inline-flex">All battles</Link>
          </div>
        </>
      ) : (
        <p className="text-fg-muted">{retrying ? "Battle's busy — retrying…" : "Joining battle…"}</p>
      )}
    </div>
  );
}
