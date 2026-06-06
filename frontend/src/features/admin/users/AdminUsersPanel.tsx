"use client";

import { useCallback, useEffect, useState } from "react";

import { CreateUserRequest, type UserResponse } from "../../../lib/api";
import { api } from "../../../lib/api/wrapper";
import { errorMessage, panelStyles, slugify } from "../shared";
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
    <section aria-label="Admin users" style={panelStyles.panel}>
      <div>
        <h2>Users</h2>
        <p>Manage lecturer and student application accounts.</p>
      </div>
      {error ? <div role="alert" style={panelStyles.alert}>{error}</div> : null}
      <div style={panelStyles.grid}>
        <CreateUserForm onCreated={loadUsers} role={CreateUserRequest.role.LECTURER} />
        <CreateUserForm onCreated={loadUsers} role={CreateUserRequest.role.STUDENT} />
      </div>
      {isLoading ? <p aria-busy="true">Loading users...</p> : null}
      <div style={{ overflowX: "auto" }}>
        <table data-testid="admin-users-table" style={panelStyles.table}>
          <thead>
            <tr>
              <th style={panelStyles.th}>Name</th>
              <th style={panelStyles.th}>Email</th>
              <th style={panelStyles.th}>Role</th>
              <th style={panelStyles.th}>State</th>
              <th style={panelStyles.th}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr data-testid={`admin-user-row-${slugify(user.email.split("@")[0])}`} key={user.id}>
                <td style={panelStyles.td}>{user.fullName}</td>
                <td style={panelStyles.td}>{user.email}</td>
                <td style={panelStyles.td}>{user.role}</td>
                <td style={panelStyles.td}>{user.isActive ? "Active" : "Inactive"}</td>
                <td style={panelStyles.td}>
                  <div style={panelStyles.stack}>
                    <button
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
