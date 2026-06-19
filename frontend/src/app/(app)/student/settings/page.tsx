import { LanguagePreference } from "../../../../features/glossary/LanguagePreference";

export default function StudentSettingsPage() {
  return (
    <section className="grid gap-4">
      <h1 className="m-0 text-2xl font-semibold text-text">Settings</h1>
      <LanguagePreference />
    </section>
  );
}
