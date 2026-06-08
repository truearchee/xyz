'use client';

import {
  ApiError,
  OpenAPI,
  type SectionAssetResponse,
} from './index';
import type { ApiRequestOptions } from './core/ApiRequestOptions';
import type { ApiResult } from './core/ApiResult';
import { AuthRequiredError, ForbiddenError } from './wrapper';
import { getSupabaseBrowserClient } from '../supabase/client';

type UploadSectionAssetInput = {
  moduleId: string;
  sectionId: string;
  file: File;
  signal?: AbortSignal;
};

type ReplaceSectionAssetInput = UploadSectionAssetInput & {
  assetId: string;
};

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
    file: File;
    signal?: AbortSignal;
  },
): Promise<SectionAssetResponse> {
  const token = await getBearerToken(request);
  const formData = new FormData();
  formData.append(FILE_FIELD_NAME, input.file);

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
    return body as SectionAssetResponse;
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
    { file, signal },
  );
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
  );
}
