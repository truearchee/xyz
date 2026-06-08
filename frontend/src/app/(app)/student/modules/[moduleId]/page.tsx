import { StudentModuleDetail } from "../../../../../features/content/student/StudentModuleDetail";

type StudentModulePageProps = {
  params: Promise<{
    moduleId: string;
  }>;
};

export default async function StudentModulePage({ params }: StudentModulePageProps) {
  const { moduleId } = await params;

  return <StudentModuleDetail moduleId={moduleId} />;
}
