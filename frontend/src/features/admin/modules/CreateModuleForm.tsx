"use client";

import { useState, type FormEvent } from "react";

import { ModuleScheduleInput, SessionPatternEntry, type UserResponse } from "../../../lib/api";
import { api } from "../../../lib/api/wrapper";
import { errorMessage, panelStyles } from "../shared";

type CreateModuleFormProps = {
  lecturers: UserResponse[];
  onCreated: (moduleId: string) => Promise<void>;
};

// Stage 5.5a: module creation is schedule-driven. This form sends a fixed default weekly pattern
// (Mon/Tue/Wed lectures, Thu lab, Fri quiz day). The interactive weekly-pattern picker + creation
// preview is the Stage 5.5e thin-UI deliverable; this keeps creation working against the new contract.
const DEFAULT_SESSION_PATTERN: SessionPatternEntry[] = [
  { weekday: SessionPatternEntry.weekday.MONDAY, sectionType: SessionPatternEntry.sectionType.LECTURE },
  { weekday: SessionPatternEntry.weekday.TUESDAY, sectionType: SessionPatternEntry.sectionType.LECTURE },
  { weekday: SessionPatternEntry.weekday.WEDNESDAY, sectionType: SessionPatternEntry.sectionType.LECTURE },
  { weekday: SessionPatternEntry.weekday.THURSDAY, sectionType: SessionPatternEntry.sectionType.LAB },
];

export function CreateModuleForm({ lecturers, onCreated }: CreateModuleFormProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [courseStartDate, setCourseStartDate] = useState("");
  const [courseEndDate, setCourseEndDate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const module = await api.admin.createModule({
        title,
        description: description || null,
        ownerId,
        timezone,
        schedule: {
          courseStartDate,
          courseEndDate,
          weekStartDay: ModuleScheduleInput.weekStartDay.MONDAY,
          sessionPattern: DEFAULT_SESSION_PATTERN,
          quizDay: "friday",
        },
      });
      setTitle("");
      setDescription("");
      setOwnerId("");
      setTimezone("UTC");
      setCourseStartDate("");
      setCourseEndDate("");
      await onCreated(module.id);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form data-testid="create-module-form" onSubmit={submit} style={panelStyles.stack}>
      <h3>Create module</h3>
      {error ? <div role="alert" style={panelStyles.alert}>{error}</div> : null}
      <label style={panelStyles.label}>
        Title
        <input aria-label="Module title" onChange={(event) => setTitle(event.target.value)} required style={panelStyles.input} type="text" value={title} />
      </label>
      <label style={panelStyles.label}>
        Owner lecturer
        <select aria-label="Module owner lecturer" onChange={(event) => setOwnerId(event.target.value)} required style={panelStyles.input} value={ownerId}>
          <option value="">Select lecturer</option>
          {lecturers.map((lecturer) => (
            <option key={lecturer.id} value={lecturer.id}>{lecturer.fullName} ({lecturer.email})</option>
          ))}
        </select>
      </label>
      <label style={panelStyles.label}>
        Description
        <textarea aria-label="Module description" onChange={(event) => setDescription(event.target.value)} style={panelStyles.input} value={description} />
      </label>
      <label style={panelStyles.label}>
        Timezone
        <input aria-label="Module timezone" onChange={(event) => setTimezone(event.target.value)} required style={panelStyles.input} type="text" value={timezone} />
      </label>
      <div style={panelStyles.grid}>
        <label style={panelStyles.label}>
          Course starts on
          <input aria-label="Course starts on" onChange={(event) => setCourseStartDate(event.target.value)} required style={panelStyles.input} type="date" value={courseStartDate} />
        </label>
        <label style={panelStyles.label}>
          Course ends on
          <input aria-label="Course ends on" onChange={(event) => setCourseEndDate(event.target.value)} required style={panelStyles.input} type="date" value={courseEndDate} />
        </label>
      </div>
      <p style={panelStyles.hint}>
        Sections are generated from a fixed weekly pattern (Mon–Wed lectures, Thu lab, Fri quiz day). A
        configurable weekly-pattern picker and preview arrive in Stage 5.5e.
      </p>
      <button disabled={isSubmitting || lecturers.length === 0} type="submit">
        {isSubmitting ? "Creating..." : "Create module"}
      </button>
    </form>
  );
}
