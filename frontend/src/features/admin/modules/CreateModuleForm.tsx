"use client";

import { useMemo, useState, type FormEvent } from "react";

import {
  ModuleScheduleInput,
  type ModuleSchedulePreviewResponse,
  SessionPatternEntry,
  type UserResponse,
} from "../../../lib/api";
import { api } from "../../../lib/api/wrapper";
import { errorMessage, panelStyles } from "../shared";

type CreateModuleFormProps = {
  lecturers: UserResponse[];
  onCreated: (moduleId: string) => Promise<void>;
};

type Weekday = NonNullable<ModuleScheduleInput["quizDay"]>;
type SectionKind = "" | SessionPatternEntry["sectionType"];

const WEEKDAYS: Array<{ label: string; value: Weekday }> = [
  { label: "Mon", value: "monday" },
  { label: "Tue", value: "tuesday" },
  { label: "Wed", value: "wednesday" },
  { label: "Thu", value: "thursday" },
  { label: "Fri", value: "friday" },
  { label: "Sat", value: "saturday" },
  { label: "Sun", value: "sunday" },
];

export function CreateModuleForm({ lecturers, onCreated }: CreateModuleFormProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [courseStartDate, setCourseStartDate] = useState("");
  const [courseEndDate, setCourseEndDate] = useState("");
  const [weekStartDay, setWeekStartDay] = useState<ModuleScheduleInput.weekStartDay>(ModuleScheduleInput.weekStartDay.MONDAY);
  const [quizDay, setQuizDay] = useState<Weekday>("friday");
  const [pattern, setPattern] = useState<Record<Weekday, SectionKind>>({
    friday: "",
    monday: SessionPatternEntry.sectionType.LECTURE,
    saturday: "",
    sunday: "",
    thursday: SessionPatternEntry.sectionType.LAB,
    tuesday: SessionPatternEntry.sectionType.LECTURE,
    wednesday: SessionPatternEntry.sectionType.LECTURE,
  });
  const [preview, setPreview] = useState<ModuleSchedulePreviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isPreviewing, setIsPreviewing] = useState(false);

  const schedule = useMemo(
    () => ({
      courseStartDate,
      courseEndDate,
      weekStartDay,
      sessionPattern: WEEKDAYS.flatMap(({ value }) => {
        const sectionType = pattern[value];
        return sectionType ? [{ weekday: value as SessionPatternEntry.weekday, sectionType }] : [];
      }),
      quizDay,
    }),
    [courseEndDate, courseStartDate, pattern, quizDay, weekStartDay],
  );

  function resetPreview() {
    setPreview(null);
  }

  function setPatternFor(day: Weekday, sectionType: SectionKind) {
    setPattern((current) => ({ ...current, [day]: sectionType }));
    resetPreview();
  }

  async function previewSchedule() {
    setError(null);
    setIsPreviewing(true);
    try {
      setPreview(await api.admin.previewModuleSchedule(schedule));
    } catch (caught) {
      setPreview(null);
      setError(errorMessage(caught));
    } finally {
      setIsPreviewing(false);
    }
  }

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
        schedule,
      });
      setTitle("");
      setDescription("");
      setOwnerId("");
      setTimezone("UTC");
      setCourseStartDate("");
      setCourseEndDate("");
      setPreview(null);
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
          <input aria-label="Course starts on" onChange={(event) => { setCourseStartDate(event.target.value); resetPreview(); }} required style={panelStyles.input} type="date" value={courseStartDate} />
        </label>
        <label style={panelStyles.label}>
          Course ends on
          <input aria-label="Course ends on" onChange={(event) => { setCourseEndDate(event.target.value); resetPreview(); }} required style={panelStyles.input} type="date" value={courseEndDate} />
        </label>
      </div>
      <div style={panelStyles.grid}>
        <label style={panelStyles.label}>
          Week starts on
          <select
            aria-label="Week starts on"
            onChange={(event) => { setWeekStartDay(event.target.value as ModuleScheduleInput.weekStartDay); resetPreview(); }}
            style={panelStyles.input}
            value={weekStartDay}
          >
            {WEEKDAYS.map((day) => (
              <option key={day.value} value={day.value}>{day.label}</option>
            ))}
          </select>
        </label>
        <label style={panelStyles.label}>
          Quiz day
          <select
            aria-label="Quiz day"
            onChange={(event) => { setQuizDay(event.target.value as Weekday); resetPreview(); }}
            style={panelStyles.input}
            value={quizDay}
          >
            {WEEKDAYS.map((day) => (
              <option key={day.value} value={day.value}>{day.label}</option>
            ))}
          </select>
        </label>
      </div>
      <fieldset style={styles.patternFieldset}>
        <legend style={styles.legend}>Weekly pattern</legend>
        <div style={styles.patternGrid}>
          {WEEKDAYS.map((day) => (
            <label key={day.value} style={panelStyles.label}>
              {day.label}
              <select
                aria-label={`${day.label} section type`}
                onChange={(event) => setPatternFor(day.value, event.target.value as SectionKind)}
                style={panelStyles.input}
                value={pattern[day.value]}
              >
                <option value="">None</option>
                <option value={SessionPatternEntry.sectionType.LECTURE}>Lecture</option>
                <option value={SessionPatternEntry.sectionType.LAB}>Lab</option>
              </select>
            </label>
          ))}
        </div>
      </fieldset>
      <div style={styles.actions}>
        <button disabled={isPreviewing || !courseStartDate || !courseEndDate} onClick={() => void previewSchedule()} type="button">
          {isPreviewing ? "Previewing..." : "Preview sections"}
        </button>
        <button disabled={isSubmitting || lecturers.length === 0 || preview === null} type="submit">
          {isSubmitting ? "Creating..." : "Create module"}
        </button>
      </div>
      {preview ? (
        <section aria-label="Schedule preview" data-testid="module-schedule-preview" style={styles.preview}>
          <strong>{preview.weekCount} weeks</strong>
          <span>{preview.lectureCount} lectures</span>
          <span>{preview.labCount} labs</span>
          <span>{preview.fridaySectionCount} Friday sections</span>
          <span>{preview.totalSections} total sections</span>
        </section>
      ) : null}
    </form>
  );
}

const styles = {
  actions: {
    alignItems: "center",
    display: "flex",
    flexWrap: "wrap",
    gap: 10,
  },
  legend: {
    color: "#111827",
    fontSize: 14,
    fontWeight: 700,
    padding: 0,
  },
  patternFieldset: {
    border: "1px solid #d7dde8",
    borderRadius: 8,
    display: "grid",
    gap: 10,
    margin: 0,
    padding: 12,
  },
  patternGrid: {
    display: "grid",
    gap: 10,
    gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))",
  },
  preview: {
    alignItems: "center",
    background: "#f7faf9",
    border: "1px solid #cfe1da",
    borderRadius: 8,
    color: "#111827",
    display: "flex",
    flexWrap: "wrap",
    fontSize: 14,
    gap: 10,
    padding: 12,
  },
} satisfies Record<string, React.CSSProperties>;
