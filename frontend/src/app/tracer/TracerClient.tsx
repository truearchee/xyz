'use client';

import { useMemo, useState } from 'react';

import { ApiError } from '../../lib/api';
import type {
  AssetDownloadUrl,
  CurrentUserResponse,
  ModuleSummary,
  SectionAssetResponse,
  SectionListItem,
} from '../../lib/api';
import { api } from '../../lib/api/wrapper';
import { useSession } from '../../lib/session/SessionProvider';

type RawResult =
  | { ok: true; data: unknown }
  | { ok: false; status?: number; message: string; body?: unknown };

function errorStatus(caught: Error): number | undefined {
  if (!('status' in caught)) {
    return undefined;
  }

  const status = Number(caught.status);
  return Number.isFinite(status) ? status : undefined;
}

function errorBody(caught: Error): unknown {
  return 'body' in caught ? caught.body : undefined;
}

function format(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function errorResult(caught: unknown, fallback: string): RawResult {
  if (caught instanceof ApiError) {
    return {
      ok: false,
      status: caught.status,
      message: caught.message,
      body: caught.body,
    };
  }

  return {
    ok: false,
    status: caught instanceof Error ? errorStatus(caught) : undefined,
    message: caught instanceof Error ? caught.message : fallback,
    body: caught instanceof Error ? errorBody(caught) : undefined,
  };
}

function isUnauthorizedLike(result: RawResult | null): boolean {
  return result?.ok === false && (result.status === 403 || result.status === 404);
}

export default function TracerClient() {
  const { session, state, status: sessionStatus } = useSession();
  const [currentUser, setCurrentUser] = useState<CurrentUserResponse | null>(null);
  const [modules, setModules] = useState<Array<ModuleSummary>>([]);
  const [sections, setSections] = useState<Array<SectionListItem>>([]);
  const [selectedModuleId, setSelectedModuleId] = useState('');
  const [selectedSectionId, setSelectedSectionId] = useState('');
  const [assetId, setAssetId] = useState('');
  const [signedUrl, setSignedUrl] = useState('');
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [nonPdfFile, setNonPdfFile] = useState<File | null>(null);
  const [rawResult, setRawResult] = useState<RawResult | null>(null);
  const [unauthorizedResult, setUnauthorizedResult] = useState<RawResult | null>(
    null,
  );
  const [message, setMessage] = useState('');

  const role = currentUser?.role ?? 'unknown';
  const sessionLabel =
    sessionStatus === 'authenticated' ? 'logged in' : 'logged out';

  const selectedModule = useMemo(
    () => modules.find((module) => module.id === selectedModuleId) ?? null,
    [modules, selectedModuleId],
  );

  async function runAction<T>(
    label: string,
    action: () => Promise<T>,
    onSuccess?: (data: T) => void,
  ) {
    setMessage(label);
    setRawResult(null);
    setUnauthorizedResult(null);

    try {
      const data = await action();
      onSuccess?.(data);
      setRawResult({ ok: true, data });
    } catch (caught) {
      const result = errorResult(caught, `${label} failed`);
      setRawResult(result);
      if (isUnauthorizedLike(result)) {
        setUnauthorizedResult(result);
      }
    }
  }

  async function callMe() {
    await runAction('GET /me', api.me.get, setCurrentUser);
  }

  async function callModules() {
    await runAction('GET /modules', api.modules.list, (data) => {
      setModules(data);
      const firstModuleId = data[0]?.id ?? '';
      setSelectedModuleId((current) => current || firstModuleId);
    });
  }

  async function loadSections(moduleId = selectedModuleId) {
    if (!moduleId) {
      setRawResult({ ok: false, message: 'Select a module first' });
      return;
    }

    await runAction(
      'GET /modules/{moduleId}/sections',
      () => api.content.listSections(moduleId),
      (data) => {
        setSections(data);
        const firstSectionId = data[0]?.id ?? '';
        setSelectedSectionId((current) => current || firstSectionId);
      },
    );
  }

  async function getSelectedSection() {
    if (!selectedModuleId || !selectedSectionId) {
      setRawResult({ ok: false, message: 'Select module and section first' });
      return;
    }

    await runAction('GET selected section', () =>
      api.content.getSection(selectedModuleId, selectedSectionId),
    );
  }

  async function uploadSelectedFile(file: File | null, label: string) {
    if (!selectedModuleId || !selectedSectionId) {
      setRawResult({ ok: false, message: 'Select module and section first' });
      return;
    }
    if (!file) {
      setRawResult({ ok: false, message: `Choose a ${label} file first` });
      return;
    }

    await runAction(
      `upload ${label}`,
      () => api.content.uploadAsset(selectedModuleId, selectedSectionId, file),
      (data: SectionAssetResponse) => {
        setAssetId(data.id);
      },
    );
  }

  async function publishSection() {
    if (!selectedModuleId || !selectedSectionId) {
      setRawResult({ ok: false, message: 'Select module and section first' });
      return;
    }

    await runAction('publish section', () =>
      api.content.publishSection(selectedModuleId, selectedSectionId),
    );
  }

  async function requestSignedUrl() {
    if (!selectedModuleId || !selectedSectionId || !assetId) {
      setRawResult({
        ok: false,
        message: 'Select module, section, and asset first',
      });
      return;
    }

    await runAction(
      'request signed URL',
      () =>
        api.content.getAssetDownloadUrl(
          selectedModuleId,
          selectedSectionId,
          assetId,
        ),
      (data: AssetDownloadUrl) => {
        setSignedUrl(data.url);
      },
    );
  }

  function openSignedUrl() {
    if (!signedUrl) {
      setRawResult({ ok: false, message: 'Request a signed URL first' });
      return;
    }

    window.open(signedUrl, '_blank', 'noopener,noreferrer');
  }

  return (
    <main>
      <h1>Tracer</h1>

      <section>
        <h2>Session</h2>
        <p>Status: {sessionLabel}</p>
        <p>Provider status: {sessionStatus}</p>
        <p>Email: {session?.user.email ?? 'none'}</p>
        <p>Role: {role}</p>
        <p>Token present: {session?.access_token ? 'yes' : 'no'}</p>
        {state.status === 'forbidden' && state.reason ? (
          <p>Session error: {state.reason}</p>
        ) : null}
        {message ? <p>Last action: {message}</p> : null}
      </section>

      <section>
        <h2>API</h2>
        <button onClick={callMe} type="button">
          GET /me
        </button>
        <button onClick={callModules} type="button">
          GET /modules
        </button>
        <button onClick={() => void loadSections()} type="button">
          GET sections
        </button>
      </section>

      <section>
        <h2>Selection</h2>
        <label htmlFor="tracer-module">
          Module
          <select
            id="tracer-module"
            onChange={(event) => {
              setSelectedModuleId(event.target.value);
              setSelectedSectionId('');
              setSections([]);
              if (event.target.value) {
                void loadSections(event.target.value);
              }
            }}
            value={selectedModuleId}
          >
            <option value="">select module</option>
            {modules.map((module) => (
              <option key={module.id} value={module.id}>
                {module.title} ({module.id})
              </option>
            ))}
          </select>
        </label>
        <p>Selected module title: {selectedModule?.title ?? 'none'}</p>

        <label htmlFor="tracer-section">
          Section
          <select
            id="tracer-section"
            onChange={(event) => setSelectedSectionId(event.target.value)}
            value={selectedSectionId}
          >
            <option value="">select section</option>
            {sections.map((section) => (
              <option key={section.id} value={section.id}>
                {section.title} ({section.id})
              </option>
            ))}
          </select>
        </label>
        <label htmlFor="tracer-section-id-override">
          Section ID override
          <input
            id="tracer-section-id-override"
            onChange={(event) => setSelectedSectionId(event.target.value)}
            value={selectedSectionId}
          />
        </label>
        <button onClick={() => void getSelectedSection()} type="button">
          GET selected section
        </button>
      </section>

      <section>
        <h2>Upload</h2>
        <label htmlFor="tracer-pdf-file">
          PDF file
          <input
            accept="application/pdf,.pdf"
            id="tracer-pdf-file"
            onChange={(event) => setPdfFile(event.target.files?.[0] ?? null)}
            type="file"
          />
        </label>
        <button
          onClick={() => void uploadSelectedFile(pdfFile, 'PDF')}
          type="button"
        >
          upload PDF
        </button>

        <label htmlFor="tracer-non-pdf-file">
          Non-PDF file
          <input
            id="tracer-non-pdf-file"
            onChange={(event) => setNonPdfFile(event.target.files?.[0] ?? null)}
            type="file"
          />
        </label>
        <button
          onClick={() => void uploadSelectedFile(nonPdfFile, 'non-PDF')}
          type="button"
        >
          upload non-PDF
        </button>
        <button
          onClick={() => void uploadSelectedFile(pdfFile, 'student 403 probe')}
          type="button"
        >
          attempt upload as current user for student 403
        </button>
      </section>

      <section>
        <h2>Publish And Download</h2>
        <button onClick={() => void publishSection()} type="button">
          publish section
        </button>
        <label htmlFor="tracer-asset-id">
          Asset ID
          <input
            id="tracer-asset-id"
            onChange={(event) => setAssetId(event.target.value)}
            value={assetId}
          />
        </label>
        <button onClick={() => void requestSignedUrl()} type="button">
          request signed URL
        </button>
        <button onClick={openSignedUrl} type="button">
          open signed URL
        </button>
        <p>Signed URL: {signedUrl || 'none'}</p>
      </section>

      <section>
        <h2>Unauthorized State</h2>
        <p>
          403 keeps session:{' '}
          {session?.access_token ? 'session still present' : 'no session'}
        </p>
        <pre>{format(unauthorizedResult ?? 'No 403 observed')}</pre>
      </section>

      <section>
        <h2>Raw Result</h2>
        <pre>{format(rawResult ?? 'No result')}</pre>
      </section>
    </main>
  );
}
