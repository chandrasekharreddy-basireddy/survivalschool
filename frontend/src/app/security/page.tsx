import type { Metadata } from "next";

export const metadata: Metadata = { title: "Security" };

const PRACTICES = [
  { title: "Password storage", desc: "Passwords are hashed with Argon2id. We never store or log plaintext passwords." },
  { title: "Sessions", desc: "Access tokens are short-lived; refresh tokens are single-use and rotate on every renewal, so a leaked token has a narrow window." },
  { title: "Rate limiting", desc: "Login, registration, and password-reset endpoints are rate-limited per account and per IP to slow down brute-force attempts." },
  { title: "Role-based access", desc: "Every action — grading, publishing a course, assigning a role — is checked against the caller's role on the server, not just hidden in the UI." },
  { title: "Server-authoritative grading", desc: "Exam and quiz scores are computed and stored on the server. Nothing about a score can be set by the client." },
  { title: "Transport security", desc: "All traffic is served over HTTPS, with standard security headers (HSTS, frame denial, content-type sniffing protection) on every response." },
];

export default function SecurityPage() {
  return (
    <div className="page-frame max-w-3xl">
      <div className="page-header">
        <h1>Security</h1>
        <p className="mt-2 text-sm text-fg-muted">How we protect your account and data.</p>
      </div>

      <ul className="space-y-6">
        {PRACTICES.map((p) => (
          <li key={p.title} className="border-b border-ink-700 pb-6 last:border-0 last:pb-0">
            <h2 className="!text-base">{p.title}</h2>
            <p className="mt-1.5 text-sm text-fg-muted">{p.desc}</p>
          </li>
        ))}
      </ul>

      <div className="mt-10 card p-5">
        <h2 className="!text-base">Reporting a vulnerability</h2>
        <p className="mt-2 text-sm text-fg-muted">
          If you believe you&rsquo;ve found a security issue, please report it to your university&rsquo;s Survival
          School administrator rather than disclosing it publicly. We take these reports seriously and will follow
          up.
        </p>
      </div>
    </div>
  );
}
