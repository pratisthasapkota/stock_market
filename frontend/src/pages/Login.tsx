import { FormEvent, useEffect, useState } from "react";
import { ApiError, api, DemoAccount } from "../lib/api";
import { useAuth } from "../lib/auth";

function ChartIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4 17.5 9 12l3.5 3.5L20 7"
        stroke="#50E3C2"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="4" cy="17.5" r="1.5" fill="#50E3C2" />
      <circle cx="9" cy="12" r="1.5" fill="#50E3C2" />
      <circle cx="12.5" cy="15.5" r="1.5" fill="#50E3C2" />
      <circle cx="20" cy="7" r="1.5" fill="#50E3C2" />
    </svg>
  );
}

function EyeIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="12" r="2.8" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M3 3l18 18" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path
        d="M10.6 5.7A9.7 9.7 0 0 1 12 5.5c6.4 0 10 6.5 10 6.5a17 17 0 0 1-3.3 4.1M6.4 6.4A17 17 0 0 0 2 12s3.6 6.5 10 6.5c1.2 0 2.2-.2 3.2-.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M9.4 9.5a3 3 0 0 0 4.2 4.2"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

interface FieldErrors {
  email?: string;
  password?: string;
}

export default function Login() {
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [demo, setDemo] = useState<DemoAccount[]>([]);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Hint list comes from the API rather than the bundle: the frontend is public,
  // so seeded passwords never ship in it. The endpoint 404s when DEMO_MODE is
  // off, which just leaves the list empty. Values are only filled on click, never
  // pre-populated, so the placeholder stays a placeholder.
  useEffect(() => {
    api
      .demoAccounts()
      .then(setDemo)
      .catch(() => setDemo([]));
  }, []);

  function validate(): boolean {
    const next: FieldErrors = {};
    if (!email.trim()) next.email = "Enter your email.";
    if (!password) next.password = "Enter your password.";
    setFieldErrors(next);
    return Object.keys(next).length === 0;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return; // guards against double submits
    setError(null);
    if (!validate()) return;
    setBusy(true);
    try {
      await signIn(email.trim(), password);
    } catch (err) {
      // keep server detail out of the UI; 401 is the only actionable case
      setError(
        err instanceof ApiError && err.status === 401
          ? "Incorrect email or password."
          : "Could not sign in. Please try again."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <header className="login-brand">
          <div className="login-logo" aria-hidden="true">
            <ChartIcon />
          </div>
          <h1 className="login-title">NEPSE INSIGHT</h1>
          <p className="login-subtitle">Stock Market Intelligence Platform</p>
        </header>

        <div className="login-divider" />

        <div className="login-welcome">
          <h2>Welcome back</h2>
          <p>Sign in to access your market dashboard.</p>
        </div>

        <form onSubmit={submit} noValidate>
          <div className="login-field">
            <label className="login-label" htmlFor="login-email">
              Email
            </label>
            <input
              id="login-email"
              className={`login-input${fieldErrors.email ? " invalid" : ""}`}
              type="text"
              autoComplete="username"
              placeholder="admin@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-invalid={Boolean(fieldErrors.email)}
              autoFocus
            />
            {fieldErrors.email && <p className="login-field-error">{fieldErrors.email}</p>}
          </div>

          <div className="login-field">
            <label className="login-label" htmlFor="login-password">
              Password
            </label>
            <div className="login-pw">
              <input
                id="login-password"
                className={`login-input${fieldErrors.password ? " invalid" : ""}`}
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={Boolean(fieldErrors.password)}
              />
              <button
                type="button"
                className="login-eye"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                aria-pressed={showPassword}
                title={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOffIcon /> : <EyeIcon />}
              </button>
            </div>
            {fieldErrors.password && <p className="login-field-error">{fieldErrors.password}</p>}
          </div>

          {error && (
            <p className="login-error" role="alert">
              {error}
            </p>
          )}

          <button className="login-submit" type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        

        <p className="login-footer">Authorized access only · Secure role-based permissions</p>
      </div>
    </div>
  );
}
