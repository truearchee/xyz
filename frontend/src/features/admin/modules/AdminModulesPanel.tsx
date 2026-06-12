"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type { ModuleMemberResponse, ModuleResponse, UserResponse } from "../../../lib/api";
import { api } from "../../../lib/api/wrapper";
import { errorMessage, panelClasses, slugify } from "../shared";
import { AssignMemberForm } from "./AssignMemberForm";
import { CreateModuleForm } from "./CreateModuleForm";

export function AdminModulesPanel() {
  const [users, setUsers] = useState<UserResponse[]>([]);
  const [modules, setModules] = useState<ModuleResponse[]>([]);
  const [members, setMembers] = useState<ModuleMemberResponse[]>([]);
  const [selectedModuleId, setSelectedModuleId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [removingUserId, setRemovingUserId] = useState<string | null>(null);

  const activeLecturers = useMemo(
    () => users.filter((user) => user.isActive && user.role === "lecturer"),
    [users],
  );

  const loadUsersAndModules = useCallback(async () => {
    setError(null);
    try {
      const [nextUsers, nextModules] = await Promise.all([
        api.admin.listUsers(),
        api.admin.listModules(),
      ]);
      setUsers(nextUsers);
      setModules(nextModules);
      if (!selectedModuleId && nextModules[0]) {
        setSelectedModuleId(nextModules[0].id);
      }
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setIsLoading(false);
    }
  }, [selectedModuleId]);

  const loadMembers = useCallback(async (moduleId: string) => {
    if (!moduleId) {
      setMembers([]);
      return;
    }
    setError(null);
    try {
      setMembers(await api.admin.listModuleMembers(moduleId));
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }, []);

  useEffect(() => {
    void loadUsersAndModules();
  }, [loadUsersAndModules]);

  useEffect(() => {
    void loadMembers(selectedModuleId);
  }, [loadMembers, selectedModuleId]);

  async function refreshAfterMutation(moduleId = selectedModuleId) {
    await loadUsersAndModules();
    if (moduleId) {
      setSelectedModuleId(moduleId);
      await loadMembers(moduleId);
    }
  }

  async function removeMember(userId: string) {
    setError(null);
    setRemovingUserId(userId);
    try {
      await api.admin.removeMember(selectedModuleId, userId);
      await refreshAfterMutation(selectedModuleId);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setRemovingUserId(null);
    }
  }

  const selectedModule = modules.find((module) => module.id === selectedModuleId);

  return (
    <section aria-label="Admin modules" className={panelClasses.panel}>
      <div className="grid gap-1">
        <h2 className="m-0 font-display text-lg font-semibold text-text">Modules</h2>
        <p className="m-0 text-sm text-text-muted">Create modules, assign active users, and archive memberships.</p>
      </div>
      {error ? <div role="alert" className={panelClasses.alert}>{error}</div> : null}
      <div className={panelClasses.grid}>
        <CreateModuleForm lecturers={activeLecturers} onCreated={refreshAfterMutation} />
        <AssignMemberForm modules={modules} onAssigned={refreshAfterMutation} users={users} />
      </div>
      {isLoading ? <p aria-busy="true" className="text-sm text-text-muted">Loading modules...</p> : null}
      <div className="min-w-0 overflow-x-auto">
        <table data-testid="admin-modules-table" className={panelClasses.table}>
          <thead>
            <tr>
              <th className={panelClasses.th}>Title</th>
              <th className={panelClasses.th}>Owner</th>
              <th className={panelClasses.th}>Timezone</th>
              <th className={panelClasses.th}>State</th>
            </tr>
          </thead>
          <tbody>
            {modules.map((module) => {
              const owner = users.find((user) => user.id === module.ownerId);
              return (
                <tr data-testid={`admin-module-row-${slugify(module.title)}`} key={module.id}>
                  <td className={panelClasses.td}>{module.title}</td>
                  <td className={panelClasses.td}>{owner ? `${owner.fullName} (${owner.email})` : module.ownerId}</td>
                  <td className={panelClasses.td}>{module.timezone}</td>
                  <td className={panelClasses.td}>{module.isActive ? "Active" : "Inactive"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <section aria-label="Module members" className={panelClasses.stack}>
        <label className={panelClasses.label}>
          Manage members for module
          <select
            aria-label="Managed module"
            onChange={(event) => setSelectedModuleId(event.target.value)}
            className={panelClasses.input}
            value={selectedModuleId}
          >
            <option value="">Select module</option>
            {modules.map((module) => (
              <option key={module.id} value={module.id}>{module.title}</option>
            ))}
          </select>
        </label>
        <h3 className="m-0 font-display text-base font-semibold text-text">{selectedModule ? `${selectedModule.title} members` : "Members"}</h3>
        <div className="min-w-0 overflow-x-auto">
          <table className={panelClasses.table}>
            <thead>
              <tr>
                <th className={panelClasses.th}>Name</th>
                <th className={panelClasses.th}>Email</th>
                <th className={panelClasses.th}>Role</th>
                <th className={panelClasses.th}>User state</th>
                <th className={panelClasses.th}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {members.map((member) => (
                <tr key={member.membershipId}>
                  <td className={panelClasses.td}>{member.fullName}</td>
                  <td className={panelClasses.td}>{member.email}</td>
                  <td className={panelClasses.td}>{member.role}</td>
                  <td className={panelClasses.td}>{member.userIsActive ? "Active" : "Inactive"}</td>
                  <td className={panelClasses.td}>
                    <button
                      className={panelClasses.buttonSecondary}
                      disabled={removingUserId === member.userId}
                      onClick={() => void removeMember(member.userId)}
                      type="button"
                    >
                      {removingUserId === member.userId ? "Removing..." : "Remove membership"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}
