"use client";

import { useState, type FormEvent } from "react";

import { CreateUserRequest } from "../../../lib/api";
import { api } from "../../../lib/api/wrapper";
import { errorMessage, panelClasses } from "../shared";

type CreateUserFormProps = {
  role: CreateUserRequest.role.LECTURER | CreateUserRequest.role.STUDENT;
  onCreated: () => Promise<void>;
};

export function CreateUserForm({ role, onCreated }: CreateUserFormProps) {
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await api.admin.createUser({
        email,
        fullName,
        password,
        role,
        timezone,
      });
      setEmail("");
      setFullName("");
      setPassword("");
      setTimezone("UTC");
      await onCreated();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setIsSubmitting(false);
    }
  }

  const label = role === CreateUserRequest.role.LECTURER ? "lecturer" : "student";

  return (
    <form data-testid={`create-${label}-form`} onSubmit={submit} className={panelClasses.stack}>
      <h3 className="m-0 font-display text-base font-semibold text-text">Create {label}</h3>
      {error ? <div role="alert" className={panelClasses.alert}>{error}</div> : null}
      <label className={panelClasses.label}>
        Email
        <input
          aria-label={`${label} email`}
          onChange={(event) => setEmail(event.target.value)}
          required
          className={panelClasses.input}
          type="email"
          value={email}
        />
      </label>
      <label className={panelClasses.label}>
        Full name
        <input
          aria-label={`${label} full name`}
          onChange={(event) => setFullName(event.target.value)}
          required
          className={panelClasses.input}
          type="text"
          value={fullName}
        />
      </label>
      <label className={panelClasses.label}>
        Password
        <input
          aria-label={`${label} password`}
          minLength={8}
          onChange={(event) => setPassword(event.target.value)}
          required
          className={panelClasses.input}
          type="password"
          value={password}
        />
      </label>
      <label className={panelClasses.label}>
        Timezone
        <input
          aria-label={`${label} timezone`}
          onChange={(event) => setTimezone(event.target.value)}
          required
          className={panelClasses.input}
          type="text"
          value={timezone}
        />
      </label>
      <button className={panelClasses.button} disabled={isSubmitting} type="submit">
        {isSubmitting ? "Creating..." : `Create ${label}`}
      </button>
    </form>
  );
}
