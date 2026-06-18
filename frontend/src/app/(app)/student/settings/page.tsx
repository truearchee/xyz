import { LanguagePreference } from "../../../../features/glossary/LanguagePreference";

export default function StudentSettingsPage() {
  return (
    <section style={{ display: "grid", gap: 16 }}>
      <h1>Settings</h1>
      <LanguagePreference />
    </section>
  );
}
