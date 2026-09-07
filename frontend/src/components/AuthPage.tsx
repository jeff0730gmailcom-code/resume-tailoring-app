import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  fetchAuthConfig,
  loginWithEmail,
  loginWithGoogle,
  registerAccount,
} from "../services/api";
import type { UserPublic } from "../types";

interface AuthPageProps {
  onSignedIn: (user: UserPublic) => void;
}

type AuthMode = "login" | "register";

function loadGoogleScript(): Promise<void> {
  if (window.google?.accounts?.id) return Promise.resolve();
  const existing = document.querySelector<HTMLScriptElement>('script[src="https://accounts.google.com/gsi/client"]');
  if (existing) {
    return new Promise((resolve, reject) => {
      if (window.google?.accounts?.id) {
        resolve();
        return;
      }
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => reject(new Error("Could not load Google Sign-In.")), { once: true });
    });
  }
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Could not load Google Sign-In."));
    document.head.appendChild(script);
  });
}

export default function AuthPage({ onSignedIn }: AuthPageProps) {
  const [mode, setMode] = useState<AuthMode>("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [googleClientId, setGoogleClientId] = useState("");
  const googleButtonRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchAuthConfig()
      .then((config) => setGoogleClientId(config.googleClientId.trim()))
      .catch(() => setGoogleClientId(""));
  }, []);

  useEffect(() => {
    if (!googleClientId) return;
    let cancelled = false;

    loadGoogleScript()
      .then(() => {
        if (cancelled || !googleButtonRef.current || !window.google?.accounts?.id) return;
        googleButtonRef.current.innerHTML = "";
        window.google.accounts.id.initialize({
          client_id: googleClientId,
          callback: async (response) => {
            setError(null);
            setIsSubmitting(true);
            try {
              const result = await loginWithGoogle(response.credential);
              onSignedIn(result.user);
            } catch (err) {
              setError(err instanceof ApiError ? err.message : "Google sign-in failed. Try again.");
            } finally {
              setIsSubmitting(false);
            }
          },
        });
        window.google.accounts.id.renderButton(googleButtonRef.current, {
          theme: "outline",
          size: "large",
          text: "continue_with",
          shape: "rectangular",
          width: 336,
        });
      })
      .catch(() => {
        if (!cancelled) setGoogleClientId("");
      });

    return () => {
      cancelled = true;
    };
  }, [googleClientId, onSignedIn]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (mode === "register") {
      if (!name.trim()) {
        setError("Name is required.");
        return;
      }
      if (password !== confirmPassword) {
        setError("Passwords do not match.");
        return;
      }
    }
    setIsSubmitting(true);
    try {
      const result =
        mode === "register"
          ? await registerAccount(name.trim(), email.trim(), password)
          : await loginWithEmail(email.trim(), password);
      onSignedIn(result.user);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign-in failed. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  const fieldClass =
    "rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/20";

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      <div className="mx-auto grid min-h-screen max-w-6xl lg:grid-cols-2">
        <section className="flex flex-col justify-between px-8 py-10 sm:px-14 sm:py-16">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-brand">Resume Tailor</p>
          <div className="max-w-md">
            <h1 className="text-5xl font-bold leading-tight text-slate-900 sm:text-6xl">Fit the resume to the role.</h1>
            <p className="mt-6 text-lg leading-relaxed text-slate-600">
              Sign in to upload a master CV, pick a template, and generate a tailored application.
            </p>
          </div>
          <p className="text-xs text-slate-400">Create application · Applications · Templates</p>
        </section>

        <section className="flex items-center justify-center px-6 py-12 sm:px-12">
          <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
            <h2 className="text-2xl font-semibold text-slate-900">
              {mode === "login" ? "Sign in" : "Create an account"}
            </h2>
            <p className="mt-2 text-sm text-slate-500">
              {mode === "login"
                ? "Return to your applications."
                : "An administrator must allow new members before they can tailor resumes."}
            </p>

            <div className="mt-8 flex rounded-lg border border-slate-200 p-1">
              <button
                type="button"
                onClick={() => {
                  setMode("login");
                  setError(null);
                }}
                className={`flex-1 rounded-md py-2 text-sm font-medium ${
                  mode === "login" ? "bg-brand text-white" : "text-slate-600"
                }`}
              >
                Sign in
              </button>
              <button
                type="button"
                onClick={() => {
                  setMode("register");
                  setError(null);
                }}
                className={`flex-1 rounded-md py-2 text-sm font-medium ${
                  mode === "register" ? "bg-brand text-white" : "text-slate-600"
                }`}
              >
                Register
              </button>
            </div>

            {googleClientId ? (
              <div className="mt-8 flex justify-center">
                <div ref={googleButtonRef} />
              </div>
            ) : null}

            <div className="my-6 flex items-center gap-3">
              <div className="h-px flex-1 bg-slate-200" />
              <span className="text-[10px] font-medium uppercase tracking-wide text-slate-400">Or by email</span>
              <div className="h-px flex-1 bg-slate-200" />
            </div>

            <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
              {mode === "register" ? (
                <label className="flex flex-col gap-1.5">
                  <span className="text-xs font-medium text-slate-600">Full name</span>
                  <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" required className={fieldClass} />
                </label>
              ) : null}
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-slate-600">Email</span>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  required
                  className={fieldClass}
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-slate-600">Password</span>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  minLength={mode === "register" ? 8 : undefined}
                  required
                  className={fieldClass}
                />
              </label>
              {mode === "register" ? (
                <label className="flex flex-col gap-1.5">
                  <span className="text-xs font-medium text-slate-600">Confirm password</span>
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    autoComplete="new-password"
                    minLength={8}
                    required
                    className={fieldClass}
                  />
                </label>
              ) : null}

              {error ? <p className="text-sm text-red-600">{error}</p> : null}

              <button
                type="submit"
                disabled={isSubmitting}
                className="mt-2 rounded-lg bg-brand px-4 py-3 text-sm font-semibold text-white hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSubmitting ? "Please wait..." : mode === "login" ? "Sign in" : "Create account"}
              </button>
            </form>
          </div>
        </section>
      </div>
    </div>
  );
}
