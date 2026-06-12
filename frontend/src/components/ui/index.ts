// Stage 4.9b — public component library barrel. Contracts frozen post-4.9 (rename/remove → ADR);
// additive growth allowed via the design-system.md changelog (ADR-047).
export { cn } from "./cn";

export { Button } from "./Button";
export { Input } from "./Input";
export { Card } from "./Card";
export { InteractiveCard } from "./InteractiveCard";
export { Badge } from "./Badge";
export { Modal } from "./Modal";
export { Table, tableRowEmphasis } from "./Table";
export { SortableHeader } from "./SortableHeader";
export { ToastProvider, useToast } from "./Toast";
export { EmptyState } from "./EmptyState";
export { LinearProgress, StepProgress, type PipelineStep } from "./Progress";

// Internal helpers (allowed per §3 — needed to implement the public set cleanly).
export { Spinner } from "./Spinner";
export { Skeleton } from "./Skeleton";
export { VisuallyHidden } from "./VisuallyHidden";

export type { ButtonVariant, ButtonSize, BadgeTone, StepState } from "./variants";
