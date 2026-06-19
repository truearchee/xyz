/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AssistantAvailabilityResponse } from '../models/AssistantAvailabilityResponse';
import type { ConversationListItem } from '../models/ConversationListItem';
import type { ConversationRead } from '../models/ConversationRead';
import type { KeysetPage_MessageRead_ } from '../models/KeysetPage_MessageRead_';
import type { MessageRead } from '../models/MessageRead';
import type { PaginatedResponse_ConversationListItem_ } from '../models/PaginatedResponse_ConversationListItem_';
import type { RenameConversationRequest } from '../models/RenameConversationRequest';
import type { SendMessageRequest } from '../models/SendMessageRequest';
import type { SendMessageResponse } from '../models/SendMessageResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AssistantService {
    /**
     * Get Assistant Availability
     * @param sectionId
     * @param authorization
     * @returns AssistantAvailabilityResponse Successful Response
     * @throws ApiError
     */
    public static getStudentAssistantAvailability(
        sectionId: string,
        authorization?: (string | null),
    ): CancelablePromise<AssistantAvailabilityResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/sections/{section_id}/assistant/availability',
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
     * Open Assistant Conversation
     * @param sectionId
     * @param authorization
     * @returns ConversationRead Successful Response
     * @throws ApiError
     */
    public static openStudentAssistantConversation(
        sectionId: string,
        authorization?: (string | null),
    ): CancelablePromise<ConversationRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/student/sections/{section_id}/assistant/conversation',
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
     * List Assistant Conversations
     * @param limit
     * @param offset
     * @param authorization
     * @returns PaginatedResponse_ConversationListItem_ Successful Response
     * @throws ApiError
     */
    public static listStudentAssistantConversations(
        limit: number = 30,
        offset?: number,
        authorization?: (string | null),
    ): CancelablePromise<PaginatedResponse_ConversationListItem_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/assistant/conversations',
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
     * List Assistant Messages
     * @param conversationId
     * @param limit
     * @param before
     * @param authorization
     * @returns KeysetPage_MessageRead_ Successful Response
     * @throws ApiError
     */
    public static listStudentAssistantMessages(
        conversationId: string,
        limit: number = 30,
        before?: (string | null),
        authorization?: (string | null),
    ): CancelablePromise<KeysetPage_MessageRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/assistant/conversations/{conversation_id}/messages',
            path: {
                'conversation_id': conversationId,
            },
            headers: {
                'Authorization': authorization,
            },
            query: {
                'limit': limit,
                'before': before,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Send Assistant Message
     * @param conversationId
     * @param requestBody
     * @param authorization
     * @returns SendMessageResponse Successful Response
     * @throws ApiError
     */
    public static sendStudentAssistantMessage(
        conversationId: string,
        requestBody: SendMessageRequest,
        authorization?: (string | null),
    ): CancelablePromise<SendMessageResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/student/assistant/conversations/{conversation_id}/messages',
            path: {
                'conversation_id': conversationId,
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
     * Retry Assistant Message
     * @param messageId
     * @param authorization
     * @returns MessageRead Successful Response
     * @throws ApiError
     */
    public static retryStudentAssistantMessage(
        messageId: string,
        authorization?: (string | null),
    ): CancelablePromise<MessageRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/student/assistant/messages/{message_id}/retry',
            path: {
                'message_id': messageId,
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
     * Get Assistant Conversation
     * @param conversationId
     * @param authorization
     * @returns ConversationListItem Successful Response
     * @throws ApiError
     */
    public static getStudentAssistantConversation(
        conversationId: string,
        authorization?: (string | null),
    ): CancelablePromise<ConversationListItem> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/assistant/conversations/{conversation_id}',
            path: {
                'conversation_id': conversationId,
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
     * Rename Assistant Conversation
     * @param conversationId
     * @param requestBody
     * @param authorization
     * @returns ConversationRead Successful Response
     * @throws ApiError
     */
    public static renameStudentAssistantConversation(
        conversationId: string,
        requestBody: RenameConversationRequest,
        authorization?: (string | null),
    ): CancelablePromise<ConversationRead> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/student/assistant/conversations/{conversation_id}',
            path: {
                'conversation_id': conversationId,
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
     * Delete Assistant Conversation
     * @param conversationId
     * @param authorization
     * @returns void
     * @throws ApiError
     */
    public static deleteStudentAssistantConversation(
        conversationId: string,
        authorization?: (string | null),
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/student/assistant/conversations/{conversation_id}',
            path: {
                'conversation_id': conversationId,
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
