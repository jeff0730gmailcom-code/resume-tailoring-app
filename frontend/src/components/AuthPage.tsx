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
          theme: "filled_black",
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

  return (
    <div className="suit-pinstripe min-h-screen text-navy">
      <div className="mx-auto grid min-h-screen max-w-6xl lg:grid-cols-2">
        <section className="flex flex-col justify-between px-8 py-10 sm:px-14 sm:py-16">
          <p className="font-sans text-[11px] font-semibold tracking-[0.42em] text-navy-600">ATELIER · PRIVATE ACCESS</p>
          <div className="max-w-md">
            <p className="font-suit text-xl italic text-navy-700">Cut to the role. Fitted to the firm.</p>
            <h1 className="mt-4 font-display text-5xl font-semibold leading-tight text-navy sm:text-6xl">Resume Tailor</h1>
            <div className="suit-gold-rule my-8 max-w-xs" />
            <p className="font-suit text-2xl leading-snug text-navy-700">
              A bespoke house for your CV. Sign in to upload a master résumé, then have it tailored — navy, gold, and ready for the next interview.
            </p>
          </div>
          <p className="font-sans text-xs tracking-widest text-navy-600">HAND-CUT · ONE MASTER CV · MANY FITS</p>
        </section>

        <section className="flex items-center justify-center px-6 py-12 text-navy sm:px-12">
          <div className="w-full max-w-sm border border-navy/10 bg-white/90 p-8 shadow-sm">
            <p className="font-sans text-[11px] font-semibold tracking-[0.35em] text-navy-600">MEMBERS&apos; ENTRANCE</p>
            <h2 className="mt-2 font-display text-3xl text-navy">
              {mode === "login" ? "Sign in" : "Open an account"}
            </h2>
            <p className="mt-2 font-suit text-lg italic text-navy-600">
              {mode === "login"
                ? "Return to the cutting room."
                : "An administrator must allow new members before they can tailor resumes."}
            </p>

            <div className="mt-8 flex rounded-sm border border-navy/15 p-1">
              <button
                type="button"
                onClick={() => {
                  setMode("login");
                  setError(null);
                }}
                className={`flex-1 py-2 font-sans text-sm font-semibold tracking-wide ${
                  mode === "login" ? "bg-navy text-ivory" : "text-navy-700"
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
                className={`flex-1 py-2 font-sans text-sm font-semibold tracking-wide ${
                  mode === "register" ? "bg-navy text-ivory" : "text-navy-700"
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
              <div className="h-px flex-1 bg-navy/15" />
              <span className="font-sans text-[10px] tracking-[0.25em] text-navy-600">OR BY EMAIL</span>
              <div className="h-px flex-1 bg-navy/15" />
            </div>

            <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
              {mode === "register" ? (
                <label className="flex flex-col gap-1.5">
                  <span className="font-sans text-xs font-semibold tracking-wide text-navy-700">Full name</span>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    autoComplete="name"
                    required
                    className="border border-navy/20 bg-white px-3 py-2.5 font-sans text-sm outline-none focus:border-gold"
                  />
                </label>
              ) : null}
              <label className="flex flex-col gap-1.5">
                <span className="font-sans text-xs font-semibold tracking-wide text-navy-700">Email</span>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  required
                  className="border border-navy/20 bg-white px-3 py-2.5 font-sans text-sm outline-none focus:border-gold"
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="font-sans text-xs font-semibold tracking-wide text-navy-700">Password</span>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  minLength={mode === "register" ? 8 : undefined}
                  required
                  className="border border-navy/20 bg-white px-3 py-2.5 font-sans text-sm outline-none focus:border-gold"
                />
              </label>
              {mode === "register" ? (
                <label className="flex flex-col gap-1.5">
                  <span className="font-sans text-xs font-semibold tracking-wide text-navy-700">Confirm password</span>
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    autoComplete="new-password"
                    minLength={8}
                    required
                    className="border border-navy/20 bg-white px-3 py-2.5 font-sans text-sm outline-none focus:border-gold"
                  />
                </label>
              ) : null}

              {error ? <p className="font-sans text-sm text-red-700">{error}</p> : null}

              <button
                type="submit"
                disabled={isSubmitting}
                className="mt-2 bg-navy px-4 py-3 font-sans text-sm font-semibold tracking-[0.18em] text-gold-200 transition-colors hover:bg-navy-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSubmitting ? "Please wait…" : mode === "login" ? "ENTER THE ATELIER" : "CREATE ACCOUNT"}
              </button>
            </form>
          </div>
        </section>
      </div>
    </div>
  );
}
