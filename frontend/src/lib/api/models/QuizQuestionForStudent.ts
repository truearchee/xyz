/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AnswerForStudent } from './AnswerForStudent';
import type { QuizOptionForStudent } from './QuizOptionForStudent';
/**
 * A question as the student sees it. ``answer`` is null until answered (then it carries the
 * correctness + explanation). No top-level ``explanation``/correctness pre-answer.
 */
export type QuizQuestionForStudent = {
    id: string;
    questionText: string;
    displayOrder: number;
    questionType: string;
    options: Array<QuizOptionForStudent>;
    answer?: (AnswerForStudent | null);
};
