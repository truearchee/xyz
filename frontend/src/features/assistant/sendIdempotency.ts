export type SendAttempt = {
  content: string;
  key: string;
};

export type SendDecision =
  | { action: "reject"; reason: "empty" | "busy" }
  | { action: "send"; attempt: SendAttempt };

type PendingLike = { status?: string | null };

export function hasPendingAssistantTurn(messages: readonly PendingLike[]): boolean {
  return messages.some((message) => message.status === "pending");
}

export function decideSendAttempt(input: {
  content: string;
  sending: boolean;
  hasPending: boolean;
  existingAttempt: SendAttempt | null | undefined;
  createKey: () => string;
}): SendDecision {
  const content = input.content.trim();
  if (!content) {
    return { action: "reject", reason: "empty" };
  }
  if (input.sending || input.hasPending) {
    return { action: "reject", reason: "busy" };
  }
  if (input.existingAttempt?.content === content) {
    return { action: "send", attempt: input.existingAttempt };
  }
  return { action: "send", attempt: { content, key: input.createKey() } };
}
