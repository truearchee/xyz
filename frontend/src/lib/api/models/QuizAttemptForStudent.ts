/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { QuizQuestionForStudent } from './QuizQuestionForStudent';
/**
 * An attempt with its snapshot questions (no provenance, no isCorrect pre-answer).
 */
export type QuizAttemptForStudent = {
    id: string;
    quizDefinitionId: string;
    status: string;
    attemptNumber: number;
    totalQuestions?: (number | null);
    questions?: Array<QuizQuestionForStudent>;
};
