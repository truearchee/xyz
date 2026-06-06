"use client";

import { useState, type FormEvent } from "react";

import { CreateUserRequest } from "../../../lib/api";
import { api } from "../../../lib/api/wrapper";
import { errorMessage, panelStyles } from "../shared";

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
    <form data-testid={`create-${label}-form`} onSubmit={submit} style={panelStyles.stack}>
      <h3>Create {label}</h3>
      {error ? <div role="alert" style={panelStyles.alert}>{error}</div> : null}
      <label style={panelStyles.label}>
        Email
        <input
          aria-label={`${label} email`}
          onChange={(event) => setEmail(event.target.value)}
          required
          style={panelStyles.input}
          type="email"
          value={email}
        />
      </label>
      <label style={panelStyles.label}>
        Full name
        <input
          aria-label={`${label} full name`}
          onChange={(event) => setFullName(event.target.value)}
          required
          style={panelStyles.input}
          type="text"
          value={fullName}
        />
      </label>
      <label style={panelStyles.label}>
        Password
        <input
          aria-label={`${label} password`}
          minLength={8}
          onChange={(event) => setPassword(event.target.value)}
          required
          style={panelStyles.input}
          type="password"
          value={password}
        />
      </label>
      <label style={panelStyles.label}>
        Timezone
        <input
          aria-label={`${label} timezone`}
          onChange={(event) => setTimezone(event.target.value)}
          required
          style={panelStyles.input}
          type="text"
          value={timezone}
        />
      </label>
      <button disabled={isSubmitting} type="submit">
        {isSubmitting ? "Creating..." : `Create ${label}`}
      </button>
    </form>
  );
}
