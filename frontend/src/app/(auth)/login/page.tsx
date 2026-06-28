'use client';

import { FormEvent, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

import { AccessDenied } from '../../../components/auth/AccessDenied';
import { cn } from '../../../components/ui/cn';
import { ForbiddenError, api } from '../../../lib/api/wrapper';
import { roleHomePath } from '../../../lib/routing/ProtectedAppLayout';
import { useSession } from '../../../lib/session/SessionProvider';
import { getSupabaseBrowserClient } from '../../../lib/supabase/client';

type FieldErrors = { email?: string; password?: string };

// Shared input visuals (mockup: 46px field, tinted fill, in-field icon). The focus ring is driven by
// :focus-within so we don't track focus in React; an error border overrides the ring (mockup parity).
const INPUT_CLASS =
  'min-w-0 flex-1 border-none bg-transparent p-0 text-[15px] text-login-ink outline-none placeholder:text-[rgba(0,0,0,0.4)]';

function fieldWrap(hasError: boolean, disabled: boolean): string {
  return cn(
    'flex h-[46px] items-center gap-[10px] rounded-[10px] border bg-login-field px-[14px] transition-[border-color,box-shadow] duration-200',
    hasError
      ? 'border-login-error'
      : 'border-[rgba(0,0,0,0.10)] focus-within:border-[rgba(0,0,0,0.34)] focus-within:shadow-[0_0_0_4px_rgba(0,0,0,0.07)]',
    disabled && 'opacity-55',
  );
}

function FieldError({ id, children }: { id: string; children: string }) {
  return (
    <p
      id={id}
      role="alert"
      className="mx-[2px] mt-[7px] mb-0 flex items-center gap-[6px] text-[13px] leading-[1.3] text-login-error"
    >
      <svg
        width="13"
        height="13"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
      <span>{children}</span>
    </p>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const { state, refreshSession } = useSession();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const nextErrors: FieldErrors = {};
    if (!email.trim()) nextErrors.email = 'Enter your email';
    if (!password) nextErrors.password = 'Enter your password';
    if (nextErrors.email || nextErrors.password) {
      setFieldErrors(nextErrors);
      setFormError(null);
      return;
    }

    setFieldErrors({});
    setFormError(null);
    setIsSubmitting(true);

    try {
      const supabase = getSupabaseBrowserClient();
      const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
      if (signInError) {
        // Real wrong-credentials signal (Supabase, before any auth-state change).
        setFormError('Incorrect email or password. Please try again.');
        return;
      }

      await refreshSession();
      const currentUser = await api.me.get();
      router.replace(roleHomePath(currentUser.role));
    } catch (caught) {
      // A deactivated account surfaces as a 403 on /me; the shared SessionProvider routes it to the
      // AccessDenied screen (render guard below), so don't show an inline banner for it.
      if (!(caught instanceof ForbiddenError)) {
        setFormError('Something went wrong. Please try again.');
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  useEffect(() => {
    if (state.status === 'authenticated') {
      router.replace(roleHomePath(state.user.role));
    }
  }, [router, state]);

  if (state.status === 'loading' || state.status === 'authenticated') {
    return <main className="grid min-h-dvh place-items-center bg-login-page text-login-ink">Loading…</main>;
  }

  if (state.status === 'forbidden') {
    return <AccessDenied email={state.email} reason={state.reason} />;
  }

  const hasEmailError = Boolean(fieldErrors.email);
  const hasPasswordError = Boolean(fieldErrors.password);

  return (
    <main className="flex min-h-dvh items-center justify-center bg-login-page p-8">
      <div className="w-full max-w-[404px] rounded-[18px] border border-[rgba(0,0,0,0.06)] bg-login-card px-9 pt-10 pb-[30px] shadow-login-card">
        {/* Brand */}
        <div className="mb-[22px] flex flex-col items-center gap-[14px]">
          <span className="inline-flex h-[46px] w-[46px] items-center justify-center rounded-[13px] bg-login-ink text-login-on-ink">
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <line x1="6" y1="6" x2="18" y2="18" />
              <line x1="18" y1="6" x2="6" y2="18" />
            </svg>
          </span>
          <span className="text-[17px] font-semibold tracking-[-0.01em] text-login-ink">XYZ Learn</span>
        </div>

        <h1 className="mt-0 mb-[22px] text-center text-[22px] font-semibold leading-[1.25] tracking-[-0.02em] text-login-ink">
          Sign in to XYZ LMS
        </h1>

        {/* Sign-in error banner (wrong credentials) */}
        {formError ? (
          <div
            role="alert"
            className="mb-5 flex animate-[xyz-rise_0.22s_ease_both] items-start gap-[9px] rounded-[10px] border border-login-error/30 bg-login-error-surface px-[13px] py-[11px] text-[13px] leading-[1.4] text-login-error"
          >
            <span className="mt-px inline-flex flex-none">
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            </span>
            <span>{formError}</span>
          </div>
        ) : null}

        <form onSubmit={signIn} noValidate>
          {/* Email */}
          <label htmlFor="email" className="mb-[7px] block text-[13px] font-semibold text-login-ink">
            Email
          </label>
          <div className={fieldWrap(hasEmailError, isSubmitting)}>
            <span className="inline-flex flex-none text-[rgba(0,0,0,0.38)]">
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
            </span>
            <input
              id="email"
              type="email"
              name="email"
              autoComplete="email"
              placeholder="Enter your email"
              value={email}
              disabled={isSubmitting}
              aria-invalid={hasEmailError || undefined}
              aria-describedby={hasEmailError ? 'email-err' : undefined}
              onChange={(event) => {
                setEmail(event.target.value);
                setFieldErrors((prev) => ({ ...prev, email: undefined }));
                setFormError(null);
              }}
              className={INPUT_CLASS}
            />
          </div>
          {fieldErrors.email ? <FieldError id="email-err">{fieldErrors.email}</FieldError> : null}

          {/* Password */}
          <label htmlFor="password" className="mt-4 mb-[7px] block text-[13px] font-semibold text-login-ink">
            Password
          </label>
          <div className={fieldWrap(hasPasswordError, isSubmitting)}>
            <span className="inline-flex flex-none text-[rgba(0,0,0,0.38)]">
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <rect x="3" y="11" width="18" height="11" rx="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
            </span>
            <input
              id="password"
              type={showPassword ? 'text' : 'password'}
              name="password"
              autoComplete="current-password"
              placeholder="Enter your password"
              value={password}
              disabled={isSubmitting}
              aria-invalid={hasPasswordError || undefined}
              aria-describedby={hasPasswordError ? 'password-err' : undefined}
              onChange={(event) => {
                setPassword(event.target.value);
                setFieldErrors((prev) => ({ ...prev, password: undefined }));
                setFormError(null);
              }}
              className={INPUT_CLASS}
            />
            <button
              type="button"
              onClick={() => setShowPassword((prev) => !prev)}
              aria-label={showPassword ? 'Hide characters' : 'Show characters'}
              // Visual stays the 18px icon; before:-inset extends the tap target to ~44px (a11y) without
              // affecting layout or the hover highlight (which lives on the button's own box).
              className="relative -m-1 ml-0 inline-flex flex-none rounded-[7px] p-1 text-[rgba(0,0,0,0.42)] before:absolute before:-inset-[9px] before:content-[''] hover:bg-[rgba(0,0,0,0.05)]"
            >
              {showPassword ? (
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 10 8 10 8a13.16 13.16 0 0 1-1.67 2.68" />
                  <path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61" />
                  <line x1="2" y1="2" x2="22" y2="22" />
                  <path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" />
                </svg>
              ) : (
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
              )}
            </button>
          </div>
          {fieldErrors.password ? <FieldError id="password-err">{fieldErrors.password}</FieldError> : null}

          {/* Sign in */}
          <button
            type="submit"
            disabled={isSubmitting}
            className={cn(
              'mt-[22px] inline-flex h-[46px] w-full items-center justify-center gap-[9px] rounded-full bg-login-ink text-[15px] font-semibold tracking-[-0.01em] text-login-on-ink transition-[background-color,transform] duration-200 enabled:hover:bg-login-ink-hover',
              isSubmitting ? 'cursor-default opacity-[0.82]' : 'cursor-pointer',
            )}
          >
            {isSubmitting ? (
              <span
                className="inline-block h-[15px] w-[15px] animate-[spin_0.7s_linear_infinite] rounded-full border-2 border-[rgba(242,242,242,0.4)] border-t-login-on-ink"
                aria-hidden="true"
              />
            ) : null}
            <span>{isSubmitting ? 'Signing in…' : 'Sign in'}</span>
          </button>
        </form>

        {/* Helper lines (static text — no self-registration, no password reset) */}
        <div className="mt-[22px] flex flex-col gap-[5px] text-center">
          <p className="m-0 text-[13px] leading-[1.5] text-[rgba(0,0,0,0.62)]">
            Forgot your password? Contact your administrator.
          </p>
          <p className="m-0 text-[13px] leading-[1.5] text-[rgba(0,0,0,0.58)]">
            Accounts are created by your administrator.
          </p>
        </div>
      </div>
    </main>
  );
}
