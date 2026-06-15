import { AssignedModulesList } from "../../../features/modules/AssignedModulesList";

export default function StudentPage() {
  return (
    <section className="grid gap-4">
      <h1 className="m-0 font-display text-2xl font-semibold text-text">Student</h1>
      <AssignedModulesList moduleHrefPrefix="/student/modules" />
    </section>
  );
}
