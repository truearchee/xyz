/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * The completed-attempt result view (score + counts).
 */
export type QuizAttemptResult = {
    id: string;
    status: string;
    scorePercentage?: (string | null);
    correctCount?: (number | null);
    incorrectCount?: (number | null);
    totalQuestions?: (number | null);
    completedAt?: (string | null);
};
