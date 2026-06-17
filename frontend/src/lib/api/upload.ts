'use client';

import {
  ApiError,
  OpenAPI,
  type SectionAssetResponse,
  type TranscriptMeta,
} from './index';
import type { ApiRequestOptions } from './core/ApiRequestOptions';
import type { ApiResult } from './core/ApiResult';
import { AuthRequiredError, ForbiddenError } from './wrapper';
import { getSupabaseBrowserClient } from '../supabase/client';

type UploadSectionAssetInput = {
  moduleId: string;
  sectionId: string;
  file: File;
  dueAt?: string | null;
  signal?: AbortSignal;
};

type ReplaceSectionAssetInput = UploadSectionAssetInput & {
  assetId: string;
};

type UploadTranscriptInput = UploadSectionAssetInput;

const FILE_FIELD_NAME = 'file';

async function redirectToLogin() {
  const supabase = getSupabaseBrowserClient();
  await supabase.auth.signOut();

  if (typeof window !== 'undefined') {
    window.location.assign('/login');
  }
}

async function getBearerToken(request: ApiRequestOptions): Promise<string> {
  const tokenResolver = OpenAPI.TOKEN;
  const token =
    typeof tokenResolver === 'function'
      ? await tokenResolver(request)
      : tokenResolver;

  if (!token) {
    await redirectToLogin();
    throw new AuthRequiredError();
  }

  return token;
}

function sectionAssetPath(input: {
  moduleId: string;
  sectionId: string;
  assetId?: string;
}): string {
  const base = `/modules/${encodeURIComponent(input.moduleId)}/sections/${encodeURIComponent(
    input.sectionId,
  )}/assets`;

  if (!input.assetId) {
    return base;
  }

  return `${base}/${encodeURIComponent(input.assetId)}`;
}

function sectionTranscriptPath(input: {
  moduleId: string;
  sectionId: string;
}): string {
  return `/modules/${encodeURIComponent(input.moduleId)}/sections/${encodeURIComponent(
    input.sectionId,
  )}/transcript`;
}

function uploadUrl(path: string): string {
  return `${OpenAPI.BASE}${path}`;
}

async function responseBody(response: Response): Promise<unknown> {
  if (response.status === 204) {
    return undefined;
  }

  const contentType = response.headers.get('Content-Type')?.toLowerCase() ?? '';
  if (contentType.startsWith('application/json') || contentType.startsWith('application/problem+json')) {
    return response.json();
  }

  return response.text();
}

function apiError(
  request: ApiRequestOptions,
  response: Response,
  body: unknown,
  message: string,
): ApiError {
  const result: ApiResult = {
    body,
    ok: response.ok,
    status: response.status,
    statusText: response.statusText,
    url: response.url,
  };

  return new ApiError(request, result, message);
}

async function uploadMultipart(
  request: ApiRequestOptions,
  input: {
    dueAt?: string | null;
    file: File;
    signal?: AbortSignal;
  },
): Promise<unknown> {
  const token = await getBearerToken(request);
  const formData = new FormData();
  formData.append(FILE_FIELD_NAME, input.file);
  if (input.dueAt !== undefined && input.dueAt !== null) {
    formData.append('dueAt', input.dueAt);
  }

  const response = await fetch(uploadUrl(request.url), {
    body: formData,
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
    },
    method: request.method,
    signal: input.signal,
  });
  const body = await responseBody(response);

  if (response.ok) {
    return body;
  }

  if (response.status === 401) {
    await redirectToLogin();
    throw new AuthRequiredError(response.statusText || 'Unauthorized');
  }

  if (response.status === 403) {
    throw new ForbiddenError(response.statusText || 'Forbidden', body);
  }

  const statusMessages: Record<number, string> = {
    400: 'Bad Request',
    404: 'Not Found',
    409: 'Conflict',
    413: 'Payload Too Large',
    422: 'Validation Error',
    500: 'Internal Server Error',
    502: 'Bad Gateway',
    503: 'Service Unavailable',
  };

  throw apiError(
    request,
    response,
    body,
    statusMessages[response.status] ?? response.statusText ?? 'Upload failed',
  );
}

export async function uploadSectionAsset({
  dueAt,
  moduleId,
  sectionId,
  file,
  signal,
}: UploadSectionAssetInput): Promise<SectionAssetResponse> {
  const path = sectionAssetPath({ moduleId, sectionId });

  return uploadMultipart(
    {
      method: 'POST',
      url: path,
    },
    { dueAt, file, signal },
  ) as Promise<SectionAssetResponse>;
}

export async function replaceSectionAsset({
  moduleId,
  sectionId,
  assetId,
  file,
  signal,
}: ReplaceSectionAssetInput): Promise<SectionAssetResponse> {
  const path = sectionAssetPath({ assetId, moduleId, sectionId });

  return uploadMultipart(
    {
      method: 'PUT',
      url: path,
    },
    { file, signal },
  ) as Promise<SectionAssetResponse>;
}

export async function uploadTranscript({
  moduleId,
  sectionId,
  file,
  signal,
}: UploadTranscriptInput): Promise<TranscriptMeta> {
  const path = sectionTranscriptPath({ moduleId, sectionId });

  return uploadMultipart(
    {
      method: 'POST',
      url: path,
    },
    { file, signal },
  ) as Promise<TranscriptMeta>;
}
