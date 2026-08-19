import type { Metadata } from "next";

export const metadata: Metadata = { title: "Terms" };

export default function TermsPage() {
  return (
    <div className="page-frame max-w-3xl">
      <div className="page-header">
        <h1>Terms of use</h1>
        <p className="mt-2 text-sm text-fg-muted">Last updated August 2026.</p>
      </div>

      <div className="space-y-8 text-[0.95rem] leading-relaxed text-fg-muted">
        <section>
          <h2>Registration</h2>
          <p className="mt-2">
            New accounts can be created during the weekly registration window, which opens every Thursday (IST).
            Outside that window, registration is closed and the platform will tell you when it next opens. This
            applies to new student sign-ups only — existing accounts can sign in at any time.
          </p>
        </section>

        <section>
          <h2>Exams</h2>
          <p className="mt-2">
            Weekend exams are timed by our servers, not your device — the clock keeps running even if you close
            the tab. Most exams require fullscreen and log integrity events (tab switches, fullscreen exits) for
            instructor review. Submitting on time and answering honestly is on you; we don&rsquo;t claim our
            monitoring catches everything, and instructors may act on flagged attempts at their discretion.
          </p>
        </section>

        <section>
          <h2>Certificates</h2>
          <p className="mt-2">
            A certificate is issued automatically to the top-scoring students in a graded exam who pass the
            course&rsquo;s pass mark. Every certificate has a public verification page and a QR code — anyone,
            including an employer, can check it&rsquo;s genuine without needing an account.
          </p>
        </section>

        <section>
          <h2>Acceptable use</h2>
          <p className="mt-2">
            Don&rsquo;t share your account, attempt to bypass exam timing or integrity monitoring, or use the
            platform to harass other users in chat or discussions. We can suspend accounts that do.
          </p>
        </section>

        <section>
          <h2>Changes</h2>
          <p className="mt-2">
            We may update these terms as the platform changes. Material changes will be reflected here with an
            updated date.
          </p>
        </section>
      </div>
    </div>
  );
}
