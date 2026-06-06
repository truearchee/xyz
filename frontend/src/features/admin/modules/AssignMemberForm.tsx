"use client";

import { useState, type FormEvent } from "react";

import { AssignMemberRequest, type ModuleResponse, type UserResponse } from "../../../lib/api";
import { api } from "../../../lib/api/wrapper";
import { errorMessage, panelStyles } from "../shared";

type AssignMemberFormProps = {
  modules: ModuleResponse[];
  users: UserResponse[];
  onAssigned: (moduleId: string) => Promise<void>;
};

export function AssignMemberForm({ modules, users, onAssigned }: AssignMemberFormProps) {
  const [moduleId, setModuleId] = useState("");
  const [role, setRole] = useState<AssignMemberRequest.role>(AssignMemberRequest.role.LECTURER);
  const [userId, setUserId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const eligibleUsers = users.filter((user) => user.isActive && user.role === role);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await api.admin.assignMember(moduleId, { userId, role });
      setUserId("");
      await onAssigned(moduleId);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form data-testid="assign-member-form" onSubmit={submit} style={panelStyles.stack}>
      <h3>Assign member</h3>
      {error ? <div role="alert" style={panelStyles.alert}>{error}</div> : null}
      <label style={panelStyles.label}>
        Module
        <select aria-label="Assignment module" onChange={(event) => setModuleId(event.target.value)} required style={panelStyles.input} value={moduleId}>
          <option value="">Select module</option>
          {modules.map((module) => (
            <option key={module.id} value={module.id}>{module.title}</option>
          ))}
        </select>
      </label>
      <label style={panelStyles.label}>
        Role
        <select
          aria-label="Assignment role"
          onChange={(event) => {
            setRole(event.target.value as AssignMemberRequest.role);
            setUserId("");
          }}
          required
          style={panelStyles.input}
          value={role}
        >
          <option value={AssignMemberRequest.role.LECTURER}>Lecturer</option>
          <option value={AssignMemberRequest.role.STUDENT}>Student</option>
        </select>
      </label>
      <label style={panelStyles.label}>
        User
        <select aria-label="Assignment user" onChange={(event) => setUserId(event.target.value)} required style={panelStyles.input} value={userId}>
          <option value="">Select {role}</option>
          {eligibleUsers.map((user) => (
            <option key={user.id} value={user.id}>{user.fullName} ({user.email})</option>
          ))}
        </select>
      </label>
      <button disabled={isSubmitting || modules.length === 0 || eligibleUsers.length === 0} type="submit">
        {isSubmitting ? "Assigning..." : "Assign member"}
      </button>
    </form>
  );
}
