import type { AxiosError } from 'axios';

export type NormalizedApiError = {
  title: string;
  message: string;
  type: 'error' | 'warning' | 'info';
  fields?: Record<string, string>;
  retry?: boolean;
  status?: number;
};

function isAxiosError(error: unknown): error is AxiosError {
  return typeof error === 'object' && error !== null && 'isAxiosError' in error;
}

function responseDetail(payload: unknown): { message?: string; fields?: Record<string, string> } {
  if (!payload || typeof payload !== 'object' || !('detail' in payload)) return {};
  const detail = (payload as { detail?: unknown }).detail;
  if (Array.isArray(detail)) {
    const fields: Record<string, string> = {};
    for (const item of detail) {
      if (!item || typeof item !== 'object') continue;
      const value = item as { loc?: unknown; msg?: unknown };
      const location = Array.isArray(value.loc) ? value.loc.filter((part) => part !== 'body').join('.') : 'request';
      if (typeof value.msg === 'string' && !fields[location]) fields[location] = 'Please check this field.';
    }
    return { fields };
  }
  if (typeof detail === 'string') return { message: detail };
  if (typeof detail === 'object' && detail !== null) {
    const value = detail as { message?: unknown; fields?: unknown };
    return {
      message: typeof value.message === 'string' ? value.message : undefined,
      fields: value.fields && typeof value.fields === 'object'
        ? Object.fromEntries(Object.entries(value.fields).filter(([, item]) => typeof item === 'string')) as Record<string, string>
        : undefined,
    };
  }
  return {};
}

export function normalizeApiError(error: unknown): NormalizedApiError {
  if (isAxiosError(error)) {
    const status = error.response?.status;
    const payload = error.response?.data;
    const detail = responseDetail(payload);

    if (status === 401) {
      return {
        title: 'Sign in required',
        message: detail.message || 'You need to be signed in to access this feature. Please sign in or create an account.',
        type: 'info',
        status,
      };
    }
    if (status === 403) {
      return { title: 'Access denied', message: detail.message || 'You do not have permission to perform this action.', type: 'error', status };
    }
    if (status === 404) {
      return { title: 'Not found', message: detail.message || 'This record is no longer available.', type: 'warning', status };
    }
    if (status === 409) {
      return { title: 'Conflict', message: detail.message || 'This change conflicts with the current record state. Please refresh and try again.', type: 'warning', status };
    }
    if (status === 413) {
      return { title: 'File too large', message: detail.message || 'This file is larger than the supported upload limit.', type: 'error', status };
    }
    if (status === 429) {
      return { title: 'Too many attempts', message: detail.message || 'Too many requests have been made. Please wait a moment and try again.', type: 'warning', status };
    }
    if (status === 422) {
      return { title: 'Check your input', message: detail.message || 'Please review the highlighted fields and try again.', type: 'warning', fields: detail.fields };
    }
    if (status === 500 || status === 502 || status === 503) {
      return { title: 'Service unavailable', message: detail.message || 'We could not complete the request. Please try again in a moment.', type: 'error', retry: true, status };
    }
    if (error.code === 'ECONNABORTED' || error.code === 'ERR_NETWORK') {
      return { title: 'Connection issue', message: 'We could not reach the server. Please check your connection and try again.', type: 'error', retry: true };
    }
    return { title: 'Request failed', message: detail.message || 'The request could not be completed. Please try again.', type: 'error', retry: true, status };
  }

  if (error instanceof Error && error.message) {
    return { title: 'Something went wrong', message: error.message, type: 'error', retry: true };
  }

  return { title: 'Something went wrong', message: 'The request could not be completed. Please try again.', type: 'error', retry: true };
}
