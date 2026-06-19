import { Suspense } from "react";

import { AssistantWorkspace } from "../../../../features/assistant/workspace/AssistantWorkspace";

export default function AssistantWorkspacePage() {
  // Suspense boundary: AssistantWorkspace reads ?new=1 (useSearchParams) to auto-open the lecture picker.
  return (
    <Suspense>
      <AssistantWorkspace />
    </Suspense>
  );
}
