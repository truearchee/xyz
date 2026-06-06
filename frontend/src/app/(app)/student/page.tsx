import { AssignedModulesList } from "../../../features/modules/AssignedModulesList";

export default function StudentPage() {
  return (
    <section style={{ display: "grid", gap: 16 }}>
      <h1>Student</h1>
      <AssignedModulesList />
    </section>
  );
}
