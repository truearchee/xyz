/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One current-student mistake as shown in the module mistakes-bank.
 */
export type MistakeBankItem = {
    id: string;
    moduleId: string;
    moduleSectionId: string;
    sourceQuizDefinitionId: string;
    questionSnapshot: Record<string, any>;
    answerOptionsSnapshot: Record<string, any>;
    selectedWrongAnswer: string;
    correctAnswer: string;
    explanation?: (string | null);
    retakeCorrectCount: number;
    showInRetakePrefix: boolean;
    updatedAt: string;
};
