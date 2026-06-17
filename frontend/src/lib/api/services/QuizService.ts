/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AnswerFeedback } from '../models/AnswerFeedback';
import type { AnswerSubmission } from '../models/AnswerSubmission';
import type { ExamPrepScopeSummary } from '../models/ExamPrepScopeSummary';
import type { PaginatedResponse_MistakeBankItem_ } from '../models/PaginatedResponse_MistakeBankItem_';
import type { QuizAttemptForStudent } from '../models/QuizAttemptForStudent';
import type { QuizAttemptResult } from '../models/QuizAttemptResult';
import type { QuizAttemptsSummary } from '../models/QuizAttemptsSummary';
import type { QuizAvailabilityResponse } from '../models/QuizAvailabilityResponse';
import type { RecapScopeRequest } from '../models/RecapScopeRequest';
import type { ScopeAvailabilityResponse } from '../models/ScopeAvailabilityResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class QuizService {
    /**
     * Get Quiz Availability
     * @param sectionId
     * @param authorization
     * @returns QuizAvailabilityResponse Successful Response
     * @throws ApiError
     */
    public static getStudentQuizAvailability(
        sectionId: string,
        authorization?: (string | null),
    ): CancelablePromise<QuizAvailabilityResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/sections/{section_id}/quiz/availability',
            path: {
                'section_id': sectionId,
            },
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Start Quiz
     * @param sectionId
     * @param authorization
     * @returns QuizAttemptForStudent Successful Response
     * @throws ApiError
     */
    public static startStudentQuiz(
        sectionId: string,
        authorization?: (string | null),
    ): CancelablePromise<QuizAttemptForStudent> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/student/sections/{section_id}/quiz/start',
            path: {
                'section_id': sectionId,
            },
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Quiz Attempt
     * @param attemptId
     * @param authorization
     * @returns QuizAttemptForStudent Successful Response
     * @throws ApiError
     */
    public static getStudentQuizAttempt(
        attemptId: string,
        authorization?: (string | null),
    ): CancelablePromise<QuizAttemptForStudent> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/quiz/attempts/{attempt_id}',
            path: {
                'attempt_id': attemptId,
            },
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Answer Quiz Question
     * @param attemptId
     * @param requestBody
     * @param authorization
     * @returns AnswerFeedback Successful Response
     * @throws ApiError
     */
    public static answerStudentQuizQuestion(
        attemptId: string,
        requestBody: AnswerSubmission,
        authorization?: (string | null),
    ): CancelablePromise<AnswerFeedback> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/student/quiz/attempts/{attempt_id}/answer',
            path: {
                'attempt_id': attemptId,
            },
            headers: {
                'Authorization': authorization,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Complete Quiz
     * @param attemptId
     * @param authorization
     * @returns QuizAttemptResult Successful Response
     * @throws ApiError
     */
    public static completeStudentQuiz(
        attemptId: string,
        authorization?: (string | null),
    ): CancelablePromise<QuizAttemptResult> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/student/quiz/attempts/{attempt_id}/complete',
            path: {
                'attempt_id': attemptId,
            },
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Quiz Attempts Summary
     * @param sectionId
     * @param authorization
     * @returns QuizAttemptsSummary Successful Response
     * @throws ApiError
     */
    public static getStudentQuizAttemptsSummary(
        sectionId: string,
        authorization?: (string | null),
    ): CancelablePromise<QuizAttemptsSummary> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/sections/{section_id}/quiz/attempts',
            path: {
                'section_id': sectionId,
            },
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Recap Availability
     * @param moduleId
     * @param requestBody
     * @param authorization
     * @returns ScopeAvailabilityResponse Successful Response
     * @throws ApiError
     */
    public static getStudentRecapAvailability(
        moduleId: string,
        requestBody: RecapScopeRequest,
        authorization?: (string | null),
    ): CancelablePromise<ScopeAvailabilityResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/student/modules/{module_id}/recap-quiz/availability',
            path: {
                'module_id': moduleId,
            },
            headers: {
                'Authorization': authorization,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Start Recap Quiz
     * @param moduleId
     * @param requestBody
     * @param authorization
     * @returns QuizAttemptForStudent Successful Response
     * @throws ApiError
     */
    public static startStudentRecapQuiz(
        moduleId: string,
        requestBody: RecapScopeRequest,
        authorization?: (string | null),
    ): CancelablePromise<QuizAttemptForStudent> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/student/modules/{module_id}/recap-quiz/start',
            path: {
                'module_id': moduleId,
            },
            headers: {
                'Authorization': authorization,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Exam Prep Scopes
     * @param moduleId
     * @param authorization
     * @returns ExamPrepScopeSummary Successful Response
     * @throws ApiError
     */
    public static listStudentExamPrepScopes(
        moduleId: string,
        authorization?: (string | null),
    ): CancelablePromise<Array<ExamPrepScopeSummary>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/modules/{module_id}/exam-prep-scopes',
            path: {
                'module_id': moduleId,
            },
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Start Exam Prep Quiz
     * @param scopeId
     * @param authorization
     * @returns QuizAttemptForStudent Successful Response
     * @throws ApiError
     */
    public static startStudentExamPrepQuiz(
        scopeId: string,
        authorization?: (string | null),
    ): CancelablePromise<QuizAttemptForStudent> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/student/assessment-scopes/{scope_id}/exam-prep-quiz/start',
            path: {
                'scope_id': scopeId,
            },
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Mistakes Bank
     * @param moduleId
     * @param limit
     * @param offset
     * @param authorization
     * @returns PaginatedResponse_MistakeBankItem_ Successful Response
     * @throws ApiError
     */
    public static listStudentMistakesBank(
        moduleId: string,
        limit: number = 50,
        offset?: number,
        authorization?: (string | null),
    ): CancelablePromise<PaginatedResponse_MistakeBankItem_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/modules/{module_id}/mistakes-bank',
            path: {
                'module_id': moduleId,
            },
            headers: {
                'Authorization': authorization,
            },
            query: {
                'limit': limit,
                'offset': offset,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Start Mistakes Bank
     * @param moduleId
     * @param authorization
     * @returns QuizAttemptForStudent Successful Response
     * @throws ApiError
     */
    public static startStudentMistakesBank(
        moduleId: string,
        authorization?: (string | null),
    ): CancelablePromise<QuizAttemptForStudent> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/student/modules/{module_id}/mistakes-bank/start',
            path: {
                'module_id': moduleId,
            },
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
