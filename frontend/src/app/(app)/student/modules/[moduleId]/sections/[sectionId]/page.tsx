import { redirect } from "next/navigation";

type StudentSectionPageProps = {
  params: Promise<{
    moduleId: string;
    sectionId: string;
  }>;
};

// Post-4.9 Workstream B: summaries are now inline on the module page (no separate section page). This route
// is kept (deep-link-safe) but redirects to the module page. The target is derived ONLY from the URL params
// (no section lookup), so it reveals nothing about whether the section exists / is published / is accessible —
// the published/enrolled boundary stays enforced by the student API endpoints + the module page's
// published-only section list (E2E G4/G5/G6 + stage-3 visibility unchanged).
export default async function StudentSectionPage({ params }: StudentSectionPageProps) {
  const { moduleId } = await params;
  redirect(`/student/modules/${moduleId}`);
}
