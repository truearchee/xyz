"use client";

import { useState, type FormEvent } from "react";

import { api } from "../../../lib/api/wrapper";
import { errorMessage, panelClasses } from "../shared";

type ResetPasswordFormProps = {
  email: string;
  onReset: () => Promise<void>;
  userId: string;
};

export function ResetPasswordForm({ email, onReset, userId }: ResetPasswordFormProps) {
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    setIsSubmitting(true);
    try {
      await api.admin.resetPassword(userId, { newPassword });
      setNewPassword("");
      await onReset();
      setSuccess("Password successfully changed.");
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setIsSubmitting(false);
    }
  }

  function updatePassword(value: string) {
    setNewPassword(value);
    setError(null);
    setSuccess(null);
  }

  return (
    <form onSubmit={submit} className={panelClasses.stack}>
      {error ? <div role="alert" className={panelClasses.alert}>{error}</div> : null}
      {success ? (
        <div aria-live="polite" role="status" className={panelClasses.status}>
          {success}
        </div>
      ) : null}
      <label className={panelClasses.label}>
        New password
        <input
          aria-label={`New password for ${email}`}
          minLength={8}
          onChange={(event) => updatePassword(event.target.value)}
          required
          className={panelClasses.input}
          type="password"
          value={newPassword}
        />
      </label>
      <button className={panelClasses.buttonSecondary} disabled={isSubmitting} type="submit">
        {isSubmitting ? "Resetting..." : "Reset password"}
      </button>
    </form>
  );
}
