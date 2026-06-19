import { type ReactNode } from "react";

import { AssistantStoreProvider } from "../../../features/assistant/AssistantStoreProvider";
import { FloatingAssistant } from "../../../features/assistant/widget/FloatingAssistant";

// Wraps every /student/* page in the assistant store (single source of truth across the inline lecture
// panel, the Workspace, and the floating widget) and mounts the persistent floating widget. Already
// inside ProtectedAppLayout, which gates /student/* to the student role; the widget also self-guards on
// role. Lecturer/admin pages are unaffected (Stage 8 exclusion: no lecturer chat surfaces).
export default function StudentLayout({ children }: { children: ReactNode }) {
  return (
    <AssistantStoreProvider>
      {children}
      <FloatingAssistant />
    </AssistantStoreProvider>
  );
}
