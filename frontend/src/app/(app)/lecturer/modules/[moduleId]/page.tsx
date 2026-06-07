import { LecturerModuleDetail } from "../../../../../features/content/lecturer/LecturerModuleDetail";

type LecturerModulePageProps = {
  params: Promise<{
    moduleId: string;
  }>;
};

export default async function LecturerModulePage({ params }: LecturerModulePageProps) {
  const { moduleId } = await params;

  return <LecturerModuleDetail moduleId={moduleId} />;
}
