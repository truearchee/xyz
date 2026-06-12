"use client";

import { useCallback, useEffect, useState } from "react";

import { CreateUserRequest, type UserResponse } from "../../../lib/api";
import { api } from "../../../lib/api/wrapper";
import { errorMessage, panelClasses, slugify } from "../shared";
import { CreateUserForm } from "./CreateUserForm";
import { ResetPasswordForm } from "./ResetPasswordForm";

export function AdminUsersPanel() {
  const [users, setUsers] = useState<UserResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [deactivatingUserId, setDeactivatingUserId] = useState<string | null>(null);

  const loadUsers = useCallback(async () => {
    setError(null);
    try {
      setUsers(await api.admin.listUsers());
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadUsers();
  }, [loadUsers]);

  async function deactivate(userId: string) {
    setError(null);
    setDeactivatingUserId(userId);
    try {
      await api.admin.deactivateUser(userId);
      await loadUsers();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setDeactivatingUserId(null);
    }
  }

  return (
    <section aria-label="Admin users" className={panelClasses.panel}>
      <div className="grid gap-1">
        <h2 className="m-0 font-display text-lg font-semibold text-text">Users</h2>
        <p className="m-0 text-sm text-text-muted">Manage lecturer and student application accounts.</p>
      </div>
      {error ? <div role="alert" className={panelClasses.alert}>{error}</div> : null}
      <div className={panelClasses.grid}>
        <CreateUserForm onCreated={loadUsers} role={CreateUserRequest.role.LECTURER} />
        <CreateUserForm onCreated={loadUsers} role={CreateUserRequest.role.STUDENT} />
      </div>
      {isLoading ? <p aria-busy="true" className="text-sm text-text-muted">Loading users...</p> : null}
      <div className="overflow-x-auto">
        <table data-testid="admin-users-table" className={panelClasses.table}>
          <thead>
            <tr>
              <th className={panelClasses.th}>Name</th>
              <th className={panelClasses.th}>Email</th>
              <th className={panelClasses.th}>Role</th>
              <th className={panelClasses.th}>State</th>
              <th className={panelClasses.th}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr data-testid={`admin-user-row-${slugify(user.email.split("@")[0])}`} key={user.id}>
                <td className={panelClasses.td}>{user.fullName}</td>
                <td className={panelClasses.td}>{user.email}</td>
                <td className={panelClasses.td}>{user.role}</td>
                <td className={panelClasses.td}>{user.isActive ? "Active" : "Inactive"}</td>
                <td className={panelClasses.td}>
                  <div className={panelClasses.stack}>
                    <button
                      className={panelClasses.buttonSecondary}
                      disabled={!user.isActive || deactivatingUserId === user.id}
                      onClick={() => void deactivate(user.id)}
                      type="button"
                    >
                      {deactivatingUserId === user.id ? "Deactivating..." : "Deactivate"}
                    </button>
                    <ResetPasswordForm email={user.email} onReset={loadUsers} userId={user.id} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
