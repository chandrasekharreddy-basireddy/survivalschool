"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { PageLoader } from "@/components/PageLoader";

// The timetable feature has been retired from the product surface. This
// stub keeps the route resolving (for anyone with the URL bookmarked or
// indexed) instead of a 404, and sends them somewhere useful.
export default function TimetableRemovedPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/dashboard");
  }, [router]);
  return <div className="page-frame text-fg-muted"><PageLoader size="md" /></div>;
}
