import { AdminModulesPanel } from "../../../features/admin/modules/AdminModulesPanel";
import { AdminUsersPanel } from "../../../features/admin/users/AdminUsersPanel";

export default function AdminPage() {
  return (
    <section className="grid gap-6">
      <h1 className="m-0 font-display text-2xl font-bold text-text">Admin</h1>
      <AdminUsersPanel />
      <AdminModulesPanel />
    </section>
  );
}
