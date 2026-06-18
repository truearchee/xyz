import Link from "next/link";

import { AssignedModulesList } from "../../../features/modules/AssignedModulesList";

export default function StudentPage() {
  return (
    <section style={{ display: "grid", gap: 16 }}>
      <h1>Student</h1>
      <nav aria-label="Student navigation" style={{ display: "flex", gap: 12 }}>
        <Link href="/student/glossary" data-testid="nav-glossary">
          Glossary
        </Link>
        <Link href="/student/settings" data-testid="nav-settings">
          Settings
        </Link>
      </nav>
      <AssignedModulesList moduleHrefPrefix="/student/modules" />
    </section>
  );
}
