"use client";

import { useState } from "react";

import { UpdatePreferencesRequest } from "../../lib/api";
import { api } from "../../lib/api/wrapper";
import { useSession } from "../../lib/session/SessionProvider";

// Stage 7a: the student's definition language preference. New saves generate in this language;
// existing entries keep the language they were generated in (no surprise mass-regeneration).

const LANGUAGES: { value: UpdatePreferencesRequest.preferredLanguage; label: string }[] = [
  { value: UpdatePreferencesRequest.preferredLanguage.EN, label: "English" },
  { value: UpdatePreferencesRequest.preferredLanguage.AR, label: "Arabic (العربية)" },
  { value: UpdatePreferencesRequest.preferredLanguage.ZH, label: "Chinese (中文)" },
  { value: UpdatePreferencesRequest.preferredLanguage.ES, label: "Spanish (Español)" },
  { value: UpdatePreferencesRequest.preferredLanguage.FR, label: "French (Français)" },
];

export function LanguagePreference() {
  const { user, refreshSession } = useSession();
  const [value, setValue] = useState<string>(user?.preferredLanguage ?? "en");
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");

  async function onChange(next: string) {
    setValue(next);
    setState("saving");
    try {
      await api.me.updatePreferences({
        preferredLanguage: next as UpdatePreferencesRequest.preferredLanguage,
      });
      await refreshSession();
      setState("saved");
    } catch {
      setState("error");
    }
  }

  return (
    <section aria-label="Definition language" style={styles.block}>
      <h2 style={styles.heading}>Definition language</h2>
      <p style={styles.help}>
        New glossary definitions are written in this language. Existing terms keep theirs.
      </p>
      <label style={styles.label}>
        Language
        <select
          data-testid="language-preference"
          value={value}
          onChange={(e) => void onChange(e.target.value)}
          style={styles.input}
        >
          {LANGUAGES.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label}
            </option>
          ))}
        </select>
      </label>
      {state === "saved" ? (
        <span data-testid="language-preference-status" role="status" style={styles.ok}>
          Saved
        </span>
      ) : null}
      {state === "error" ? (
        <span role="alert" style={styles.err}>
          Couldn’t save — try again
        </span>
      ) : null}
    </section>
  );
}

const styles = {
  block: { border: "1px solid #d7dde8", borderRadius: 8, display: "grid", gap: 8, maxWidth: 420, padding: 16 },
  heading: { color: "#111827", fontSize: 16, margin: 0 },
  help: { color: "#4b5563", fontSize: 13, margin: 0 },
  label: { color: "#374151", display: "grid", fontSize: 13, fontWeight: 700, gap: 4 },
  input: { border: "1px solid #d7dde8", borderRadius: 6, fontSize: 14, minHeight: 36, padding: "0 10px" },
  ok: { color: "#065f46", fontSize: 13 },
  err: { color: "#7f1d1d", fontSize: 13 },
} satisfies Record<string, React.CSSProperties>;
