/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * The post-answer result embedded on a question once the student has answered it.
 */
export type AnswerForStudent = {
    selectedAnswerOptionId: string;
    isCorrect: boolean;
    correctAnswerOptionId: string;
    explanation?: (string | null);
};
