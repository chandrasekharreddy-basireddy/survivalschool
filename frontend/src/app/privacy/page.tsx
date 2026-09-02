import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Privacy" };

export default function PrivacyPage() {
  return (
    <div className="page-frame max-w-3xl">
      <div className="page-header">
        <h1>Privacy</h1>
        <p className="mt-2 text-sm text-fg-muted">Last updated August 2026.</p>
      </div>

      <div className="space-y-8 text-[0.95rem] leading-relaxed text-fg-muted">
        <section>
          <h2>What we collect</h2>
          <p className="mt-2">
            To run your account we store your name, email address, and a hashed password (Argon2id — we never
            store or see your plaintext password). If you use two-factor authentication we store the TOTP secret
            and hashed backup codes. Your contest and practice attempts, chat messages, and certificate
            records are stored so the platform can grade, rank, and issue credentials to you.
          </p>
        </section>

        <section>
          <h2>Exam integrity signals</h2>
          <p className="mt-2">
            During a proctored exam or elimination battle we log integrity events on the device you&rsquo;re
            using — tab switches, fullscreen exits, and similar signals — tied to that attempt. These are
            visible to staff with contest-management permissions for review. Grading itself always happens on
            our servers; nothing about your score is decided in your browser.
          </p>
        </section>

        <section>
          <h2>Who can see your data</h2>
          <p className="mt-2">
            Staff with contest-management permissions can see flagged attempts and results for contests they
            manage. Admins can see account-level information for support and moderation. We don&rsquo;t sell your
            data, and we don&rsquo;t share it with third parties beyond the services that keep the platform
            running (email delivery, file storage, and our AI provider for tutoring features and exam-question
            generation).
          </p>
        </section>

        <section>
          <h2>Your data, on request</h2>
          <p className="mt-2">
            You can download a copy of your account data at any time from{" "}
            <Link href="/settings" className="text-brand-600 underline dark:text-brand-400">
              Settings
            </Link>
            . You can also permanently delete your account and all associated data from the same page — deletion
            is immediate and irreversible, and ends every active session tied to your account.
          </p>
        </section>

        <section>
          <h2>Cookies</h2>
          <p className="mt-2">
            We don&rsquo;t use tracking or advertising cookies. Sign-in state is kept in your browser&rsquo;s local
            storage, not cookies.
          </p>
        </section>

        <section>
          <h2>Questions</h2>
          <p className="mt-2">
            If you have a question about your data, contact your university&rsquo;s Survival School administrator.
          </p>
        </section>
      </div>
    </div>
  );
}
