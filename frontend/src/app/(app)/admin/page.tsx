import { AdminModulesPanel } from "../../../features/admin/modules/AdminModulesPanel";
import { AdminUsersPanel } from "../../../features/admin/users/AdminUsersPanel";

export default function AdminPage() {
  return (
    <section style={{ display: "grid", gap: 24 }}>
      <h1>Admin</h1>
      <AdminUsersPanel />
      <AdminModulesPanel />
    </section>
  );
}
