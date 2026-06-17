"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type { ModuleMemberResponse, ModuleResponse, SectionWeekRead, UserResponse } from "../../../lib/api";
import { api } from "../../../lib/api/wrapper";
import { errorMessage, panelStyles, slugify } from "../shared";
import { AssignMemberForm } from "./AssignMemberForm";
import { CreateModuleForm } from "./CreateModuleForm";

export function AdminModulesPanel() {
  const [users, setUsers] = useState<UserResponse[]>([]);
  const [modules, setModules] = useState<ModuleResponse[]>([]);
  const [members, setMembers] = useState<ModuleMemberResponse[]>([]);
  const [weekRows, setWeekRows] = useState<SectionWeekRead[]>([]);
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

  const loadWeekRows = useCallback(async (moduleId: string) => {
    if (!moduleId) {
      setWeekRows([]);
      return;
    }
    setError(null);
    try {
      setWeekRows(await api.admin.listSectionsByWeek(moduleId, null, true));
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

  useEffect(() => {
    void loadWeekRows(selectedModuleId);
  }, [loadWeekRows, selectedModuleId]);

  async function refreshAfterMutation(moduleId = selectedModuleId) {
    await loadUsersAndModules();
    if (moduleId) {
      setSelectedModuleId(moduleId);
      await loadMembers(moduleId);
      await loadWeekRows(moduleId);
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
    <section aria-label="Admin modules" style={panelStyles.panel}>
      <div>
        <h2>Modules</h2>
        <p>Create modules, assign active users, and archive memberships.</p>
      </div>
      {error ? <div role="alert" style={panelStyles.alert}>{error}</div> : null}
      <div style={panelStyles.grid}>
        <CreateModuleForm lecturers={activeLecturers} onCreated={refreshAfterMutation} />
        <AssignMemberForm modules={modules} onAssigned={refreshAfterMutation} users={users} />
      </div>
      {isLoading ? <p aria-busy="true">Loading modules...</p> : null}
      <div style={{ overflowX: "auto" }}>
        <table data-testid="admin-modules-table" style={panelStyles.table}>
          <thead>
            <tr>
              <th style={panelStyles.th}>Title</th>
              <th style={panelStyles.th}>Owner</th>
              <th style={panelStyles.th}>Timezone</th>
              <th style={panelStyles.th}>State</th>
            </tr>
          </thead>
          <tbody>
            {modules.map((module) => {
              const owner = users.find((user) => user.id === module.ownerId);
              return (
                <tr data-testid={`admin-module-row-${slugify(module.title)}`} key={module.id}>
                  <td style={panelStyles.td}>{module.title}</td>
                  <td style={panelStyles.td}>{owner ? `${owner.fullName} (${owner.email})` : module.ownerId}</td>
                  <td style={panelStyles.td}>{module.timezone}</td>
                  <td style={panelStyles.td}>{module.isActive ? "Active" : "Inactive"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <section aria-label="Module members" style={panelStyles.stack}>
        <label style={panelStyles.label}>
          Manage members for module
          <select
            aria-label="Managed module"
            onChange={(event) => setSelectedModuleId(event.target.value)}
            style={panelStyles.input}
            value={selectedModuleId}
          >
            <option value="">Select module</option>
            {modules.map((module) => (
              <option key={module.id} value={module.id}>{module.title}</option>
            ))}
          </select>
        </label>
        <h3>{selectedModule ? `${selectedModule.title} members` : "Members"}</h3>
        <div style={{ overflowX: "auto" }}>
          <table style={panelStyles.table}>
            <thead>
              <tr>
                <th style={panelStyles.th}>Name</th>
                <th style={panelStyles.th}>Email</th>
                <th style={panelStyles.th}>Role</th>
                <th style={panelStyles.th}>User state</th>
                <th style={panelStyles.th}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {members.map((member) => (
                <tr key={member.membershipId}>
                  <td style={panelStyles.td}>{member.fullName}</td>
                  <td style={panelStyles.td}>{member.email}</td>
                  <td style={panelStyles.td}>{member.role}</td>
                  <td style={panelStyles.td}>{member.userIsActive ? "Active" : "Inactive"}</td>
                  <td style={panelStyles.td}>
                    <button
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
      <section aria-label="Resolver by-week sections" data-testid="admin-by-week-view" style={panelStyles.stack}>
        <h3>{selectedModule ? `${selectedModule.title} by week` : "Sections by week"}</h3>
        <div style={{ overflowX: "auto" }}>
          <table style={panelStyles.table}>
            <thead>
              <tr>
                <th style={panelStyles.th}>Week</th>
                <th style={panelStyles.th}>Date</th>
                <th style={panelStyles.th}>Type</th>
                <th style={panelStyles.th}>Title</th>
                <th style={panelStyles.th}>Publish</th>
              </tr>
            </thead>
            <tbody>
              {weekRows.map((section) => (
                <tr data-testid={`admin-by-week-row-${section.id}`} key={section.id}>
                  <td style={panelStyles.td}>{section.weekNumber ?? "Unstamped"}</td>
                  <td style={panelStyles.td}>{section.sessionDate ?? "No date"}</td>
                  <td style={panelStyles.td}>{section.type}</td>
                  <td style={panelStyles.td}>{section.title}</td>
                  <td style={panelStyles.td}>{section.publishStatus}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}
