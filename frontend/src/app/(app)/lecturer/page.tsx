import { AssignedModulesList } from "../../../features/modules/AssignedModulesList";

export default function LecturerPage() {
  return (
    <section style={{ display: "grid", gap: 16 }}>
      <h1>Lecturer</h1>
      <AssignedModulesList moduleHrefPrefix="/lecturer/modules" />
    </section>
  );
}
