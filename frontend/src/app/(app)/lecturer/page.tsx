import { AssignedModulesList } from "../../../features/modules/AssignedModulesList";

export default function LecturerPage() {
  return (
    <section className="grid gap-4">
      <h1 className="m-0 font-display text-2xl font-bold text-text">Lecturer</h1>
      <AssignedModulesList moduleHrefPrefix="/lecturer/modules" />
    </section>
  );
}
