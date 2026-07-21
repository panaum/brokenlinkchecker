"use client";

import { signIn } from "next-auth/react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";


function LoginContent() {
  const searchParams = useSearchParams();
  const error = searchParams.get("error");
  const email = searchParams.get("email");

  return (
    <main
      className="min-h-screen flex items-center justify-center relative overflow-hidden"
      style={{ background: "var(--surface-page)" }}
    >
      {/* Background glow */}
      <div
        className="absolute top-[-200px] left-[-200px] w-[600px] h-[600px] rounded-full opacity-30 pointer-events-none"
        style={{
          background: "var(--signal)",
          filter: "blur(120px)",
        }}
      />
      <div
        className="absolute bottom-[-100px] right-[-150px] w-[400px] h-[400px] rounded-full opacity-20 pointer-events-none"
        style={{
          background: "var(--signal)",
          filter: "blur(120px)",
        }}
      />

      {/* Login card */}
      <div
        className="relative z-10 w-full max-w-md mx-4 p-8 rounded-2xl text-center"
        style={{
          background: "var(--surface-card)",
          border: "1px solid var(--border-subtle)",
          boxShadow: "var(--elev-3)",
        }}
      >
        {/* Logo */}
        <div className="flex items-center justify-center gap-2 mb-6">
          <img
            src="/icon.png"
            alt="LinkSpy logo"
            width={40}
            height={40}
            style={{ borderRadius: 10 }}
          />
          <span
            style={{
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              fontWeight: 700,
              fontSize: "24px",
              color: "var(--text-primary)",
            }}
          >
            Link<span style={{ color: "var(--text-muted)" }}>Spy</span>
          </span>
        </div>

        {/* Title */}
        <h1
          style={{
            fontFamily: "var(--font-poppins), Poppins, sans-serif",
            fontWeight: 600,
            fontSize: "20px",
            color: "var(--text-primary)",
            marginBottom: 8,
          }}
        >
          Welcome to LinkSpy
        </h1>
        <p
          style={{
            fontFamily: "var(--font-poppins), Poppins, sans-serif",
            fontWeight: 400,
            fontSize: "14px",
            color: "var(--text-muted)",
            marginBottom: 32,
          }}
        >
          Sign in with your Apexure Google account to continue
        </p>

        {/* Error message */}
        {error === "unauthorized" && (
          <div
            className="mb-6 p-4 rounded-xl"
            style={{
              background: "rgba(224,92,92,0.1)",
              border: "1px solid rgba(224,92,92,0.3)",
            }}
          >
            <p
              style={{
                fontFamily: "var(--font-poppins), Poppins, sans-serif",
                fontWeight: 600,
                fontSize: "13px",
                color: "var(--status-broken)",
                marginBottom: 4,
              }}
            >
              Access Denied
            </p>
            <p
              style={{
                fontFamily: "var(--font-poppins), Poppins, sans-serif",
                fontWeight: 400,
                fontSize: "12px",
                color: "rgba(224,92,92,0.7)",
              }}
            >
              {email ? (
                <>
                  <strong>{email}</strong> is not an Apexure account.
                </>
              ) : (
                "Only @apexure.com accounts are allowed."
              )}
              <br />
              Please sign in with your @apexure.com email.
            </p>
          </div>
        )}

        {/* Sign in button */}
        <button
          onClick={() => signIn("google", { callbackUrl: "/" })}
          className="w-full flex items-center justify-center gap-3 px-6 py-3.5 rounded-xl transition-transform hover:scale-[1.02] active:scale-[0.98] cursor-pointer"
          style={{
            background: "var(--signal)",
            boxShadow: "var(--shadow-brand)",
            border: "1px solid rgba(255,255,255,0.1)",
            fontFamily: "var(--font-poppins), Poppins, sans-serif",
            fontSize: "15px",
            fontWeight: 600,
            color: "#fff",
          }}
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              fill="#4285F4"
            />
            <path
              d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              fill="#34A853"
            />
            <path
              d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              fill="#FBBC05"
            />
            <path
              d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              fill="#EA4335"
            />
          </svg>
          Sign in with Google
        </button>

        {/* Footer */}
        <p
          style={{
            fontFamily: "var(--font-poppins), Poppins, sans-serif",
            fontWeight: 400,
            fontSize: "11px",
            color: "var(--text-muted)",
            marginTop: 24,
          }}
        >
          Only @apexure.com accounts are authorized
        </p>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <main
          className="min-h-screen flex items-center justify-center"
          style={{ background: "var(--surface-page)" }}
        >
          <div
            style={{
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              color: "var(--text-muted)",
            }}
          >
            Loading...
          </div>
        </main>
      }
    >
      <LoginContent />
    </Suspense>
  );
}
