import type { AnalyzeResponse, Health, Report, UploadResponse } from './types';

const BASE = import.meta.env.VITE_API_URL ?? '';

async function asJson(res: Response) {
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }
  if (!res.ok) {
    const detail =
      body && typeof body === 'object' && 'detail' in body
        ? String((body as { detail: unknown }).detail)
        : `Request failed (${res.status})`;
    throw new Error(detail);
  }
  return body;
}

export async function getHealth(): Promise<Health> {
  const res = await fetch(`${BASE}/api/health`);
  return (await asJson(res)) as Health;
}

export async function uploadCsv(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append('file', file, file.name);
  const res = await fetch(`${BASE}/api/upload`, { method: 'POST', body: form });
  return (await asJson(res)) as UploadResponse;
}

export async function fetchSampleFile(): Promise<File> {
  const res = await fetch(`${BASE}/api/sample.csv`);
  if (!res.ok) throw new Error('Sample data unavailable');
  const blob = await res.blob();
  return new File([blob], 'sample_sales.csv', { type: 'text/csv' });
}

export async function analyze(dataset_id: string, objective: string): Promise<AnalyzeResponse> {
  const res = await fetch(`${BASE}/api/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dataset_id, objective }),
  });
  return (await asJson(res)) as AnalyzeResponse;
}

export async function getReport(run_id: string): Promise<Report> {
  const res = await fetch(`${BASE}/api/report/${run_id}`);
  return (await asJson(res)) as Report;
}

export async function downloadReport(run_id: string): Promise<void> {
  const res = await fetch(`${BASE}/api/report/${run_id}/download`);
  if (!res.ok) throw new Error('Download failed');
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `operon-report-${run_id}.md`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
