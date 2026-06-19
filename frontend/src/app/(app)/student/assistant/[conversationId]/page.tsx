import { AssistantWorkspaceConversation } from "../../../../../features/assistant/workspace/AssistantWorkspaceConversation";

type StudentConversationPageProps = {
  params: Promise<{ conversationId: string }>;
};

export default async function StudentConversationPage({ params }: StudentConversationPageProps) {
  const { conversationId } = await params;
  return <AssistantWorkspaceConversation conversationId={conversationId} />;
}
