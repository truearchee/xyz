import { StudentSectionDetail } from "../../../../../../../features/content/student/StudentSectionDetail";

type StudentSectionPageProps = {
  params: Promise<{
    moduleId: string;
    sectionId: string;
  }>;
};

export default async function StudentSectionPage({ params }: StudentSectionPageProps) {
  const { moduleId, sectionId } = await params;

  return <StudentSectionDetail moduleId={moduleId} sectionId={sectionId} />;
}
