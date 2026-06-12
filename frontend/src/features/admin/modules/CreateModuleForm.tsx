"use client";

import { useState, type FormEvent } from "react";

import type { UserResponse } from "../../../lib/api";
import { api } from "../../../lib/api/wrapper";
import { errorMessage, panelClasses } from "../shared";

type CreateModuleFormProps = {
  lecturers: UserResponse[];
  onCreated: (moduleId: string) => Promise<void>;
};

export function CreateModuleForm({ lecturers, onCreated }: CreateModuleFormProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [startsOn, setStartsOn] = useState("");
  const [endsOn, setEndsOn] = useState("");
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
        startsOn: startsOn || null,
        endsOn: endsOn || null,
      });
      setTitle("");
      setDescription("");
      setOwnerId("");
      setTimezone("UTC");
      setStartsOn("");
      setEndsOn("");
      await onCreated(module.id);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form data-testid="create-module-form" onSubmit={submit} className={panelClasses.stack}>
      <h3 className="m-0 font-display text-base font-semibold text-text">Create module</h3>
      {error ? <div role="alert" className={panelClasses.alert}>{error}</div> : null}
      <label className={panelClasses.label}>
        Title
        <input aria-label="Module title" onChange={(event) => setTitle(event.target.value)} required className={panelClasses.input} type="text" value={title} />
      </label>
      <label className={panelClasses.label}>
        Owner lecturer
        <select aria-label="Module owner lecturer" onChange={(event) => setOwnerId(event.target.value)} required className={panelClasses.input} value={ownerId}>
          <option value="">Select lecturer</option>
          {lecturers.map((lecturer) => (
            <option key={lecturer.id} value={lecturer.id}>{lecturer.fullName} ({lecturer.email})</option>
          ))}
        </select>
      </label>
      <label className={panelClasses.label}>
        Description
        <textarea aria-label="Module description" onChange={(event) => setDescription(event.target.value)} className={panelClasses.input} value={description} />
      </label>
      <label className={panelClasses.label}>
        Timezone
        <input aria-label="Module timezone" onChange={(event) => setTimezone(event.target.value)} required className={panelClasses.input} type="text" value={timezone} />
      </label>
      <div className={panelClasses.grid}>
        <label className={panelClasses.label}>
          Starts on
          <input aria-label="Module starts on" onChange={(event) => setStartsOn(event.target.value)} className={panelClasses.input} type="date" value={startsOn} />
        </label>
        <label className={panelClasses.label}>
          Ends on
          <input aria-label="Module ends on" onChange={(event) => setEndsOn(event.target.value)} className={panelClasses.input} type="date" value={endsOn} />
        </label>
      </div>
      <button className={panelClasses.button} disabled={isSubmitting || lecturers.length === 0} type="submit">
        {isSubmitting ? "Creating..." : "Create module"}
      </button>
    </form>
  );
}
