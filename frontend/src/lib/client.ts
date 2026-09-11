import axios from 'axios';
import { getAPIBaseURL } from './config';
import { getStoredAuthToken } from './auth';
import { normalizeApiError } from './api-errors';
export const apiClient = axios.create({
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

const storageDownloadUrls = new Map<string, Promise<string | null>>();
const resolvedPublicProfiles = new Map<string, Promise<{ profile: PublicUserProfile | null; imageUrl: string | null }>>();

apiClient.interceptors.request.use((config) => {
  const token = getStoredAuthToken();
  if (token) {
    config.headers = {
      ...(config.headers || {}),
      Authorization: `Bearer ${token}`,
    } as any;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const code = error?.response?.data?.code ?? error?.response?.data?.detail?.code;
    if (code === 'SITE_MAINTENANCE' && typeof window !== 'undefined' && window.location.pathname !== '/locked') {
      window.sessionStorage.setItem('ur-hud-return-to', `${window.location.pathname}${window.location.search}${window.location.hash}`);
      window.location.replace('/locked');
    }
    return Promise.reject(error);
  }
);

function apiUrl(path: string) {
  return `${getAPIBaseURL()}${path}`;
}

// Paper types
export interface Paper {
  id: number;
  user_id: string;
  title: string;
  course_code: string;
  course_name: string;
  college: string;
  department: string;
  institution_id?: string | null;
  campus_id?: string | null;
  college_id?: string | null;
  school_id?: string | null;
  academic_department_id?: string | null;
  programme_id?: string | null;
  programme_name_other?: string | null;
  semester?: string | null;
  examination_session?: string | null;
  year: number;
  paper_type: string;
  lecturer: string | null;
  description: string | null;
  file_key: string | null;
  file_drive_file_id?: string | null;
  file_storage_provider?: string | null;
  file_name?: string | null;
  file_size?: number | null;
  file_mime_type?: string | null;
  cover_key?: string | null;
  cover_drive_file_id?: string | null;
  cover_storage_provider?: string | null;
  cover_file_name?: string | null;
  cover_file_size?: number | null;
  cover_mime_type?: string | null;
  solution_key: string | null;
  solution_drive_file_id?: string | null;
  solution_storage_provider?: string | null;
  solution_file_name?: string | null;
  solution_file_size?: number | null;
  solution_mime_type?: string | null;
  verification_status: string;
  download_count: number | null;
  report_count: number | null;
  is_hidden: boolean | null;
  created_at: string | null;
  uploader_display_name?: string | null;
  uploader_profile_picture_key?: string | null;
}

export interface PaperListResponse {
  items: Paper[];
  total: number;
  skip: number;
  limit: number;
  data_source?: 'live' | 'cache';
}

export interface Comment {
  id: number;
  user_id: string;
  paper_id: number | null;
  book_id?: number | null;
  content: string;
  parent_id: number | null;
  upvotes: number | null;
  created_at: string | null;
}

export interface Solution {
  id: number;
  user_id: string;
  paper_id: number;
  content: string;
  file_key: string | null;
  upvotes: number | null;
  is_best: boolean | null;
  created_at: string | null;
}

export interface UserProfile {
  id: number;
  user_id: string;
  display_name: string;
  role: string;
  permissions?: string[];
  is_super_admin?: boolean;
  trust_score: number | null;
  upload_count: number | null;
  download_count: number | null;
  institution_type?: 'ur_student' | 'other_university' | null;
  university_name?: string | null;
  ur_student_code?: string | null;
  ur_verification_status?: 'not_requested' | 'pending' | 'verified' | 'rejected' | null;
  profile_picture_key?: string | null;
  phone_number?: string | null;
  college_name?: string | null;
  department_name?: string | null;
  institution_id?: string | null;
  campus_id?: string | null;
  college_id?: string | null;
  school_id?: string | null;
  academic_department_id?: string | null;
  programme_id?: string | null;
  programme_name_other?: string | null;
  year_of_study?: string | null;
  bio?: string | null;
  requested_role?: 'cp' | 'lecturer' | null;
  requested_role_status?: 'none' | 'pending' | 'approved' | 'rejected' | null;
  account_status?: string | null;
  suspension_reason?: string | null;
  suspended_until?: string | null;
  email?: string | null;
  name?: string | null;
  auth_role?: string | null;
  last_login?: string | null;
  created_at: string | null;
}

export interface PublicUserProfile {
  user_id: string;
  display_name: string;
  role: string;
  trust_score: number | null;
  upload_count: number | null;
  download_count: number | null;
  institution_type?: 'ur_student' | 'other_university' | null;
  university_name?: string | null;
  ur_verification_status?: 'not_requested' | 'pending' | 'verified' | 'rejected' | null;
  profile_picture_key?: string | null;
  college_name?: string | null;
  department_name?: string | null;
  year_of_study?: string | null;
  bio?: string | null;
  created_at: string | null;
}

export interface AcademicNode { id: string; name: string; slug: string; parent_id: string | null; active: boolean; order: number; description?: string | null; }
export interface AcademicTaxonomy { institution: AcademicNode; nodes: AcademicNode[]; }
export interface ProgrammeRecommendation { kind: 'official' | 'submission'; id: string; name: string; confidence: number; confidence_label: string; occurrences: number; campus_id: string; college_id: string; school_id: string; }

let academicTaxonomyCache: { value: AcademicTaxonomy; expiresAt: number } | null = null;
let academicTaxonomyRequest: Promise<AcademicTaxonomy> | null = null;

export async function fetchAcademicTaxonomy(): Promise<AcademicTaxonomy> {
  if (academicTaxonomyCache && academicTaxonomyCache.expiresAt > Date.now()) return academicTaxonomyCache.value;
  if (academicTaxonomyRequest) return academicTaxonomyRequest;
  academicTaxonomyRequest = apiClient.get(apiUrl('/api/v1/academics/taxonomy'))
    .then((response) => {
      const value = response.data as AcademicTaxonomy;
      academicTaxonomyCache = { value, expiresAt: Date.now() + 15 * 60 * 1000 };
      return value;
    })
    .finally(() => { academicTaxonomyRequest = null; });
  return academicTaxonomyRequest;
}
export async function fetchProgrammeRecommendations(data: { institution_id: string; campus_id: string; college_id: string; school_id: string; programme_name_other: string }): Promise<ProgrammeRecommendation[]> {
  const response = await apiClient.post(apiUrl('/api/v1/academics/programme-recommendations'), data);
  const recs = response.data.recommendations || [];
  // Normalize shape for frontend consumption
  return recs.map((r: any) => ({
    kind: r.source === 'alias' || r.source === 'official' ? 'official' : 'submission',
    id: r.programme_id || String(r.submission_id || ''),
    name: r.programme_name || r.normalized_programme_name || '',
    confidence: r.score || 0,
    confidence_label: r.match_level === 'strong' ? 'Strong match' : r.match_level === 'likely' ? 'Likely match' : r.match_level === 'possible' ? 'Possible match' : '',
    occurrences: r.occurrences || 0,
    campus_id: r.campus_id,
    college_id: r.college_id,
    school_id: r.school_id,
  })) as ProgrammeRecommendation[];
}

export interface ProgrammeCandidateItem {
  normalized_programme_name: string;
  campus_id: string;
  college_id: string;
  school_id: string;
  occurrences: number;
  best_match?: ProgrammeRecommendation | null;
  matches?: ProgrammeRecommendation[];
}

export async function fetchProgrammeCandidatesDetailed(): Promise<{ items: ProgrammeCandidateItem[] }> {
  const response = await apiClient.get(apiUrl('/api/v1/admin/hub/programme-candidates/detailed'));
  return response.data as { items: ProgrammeCandidateItem[] };
}

export async function verifyProgrammeCandidate(data: { normalized_programme_name: string; campus_id: string; college_id: string; school_id: string; programme_id: string }) {
  const response = await apiClient.post(apiUrl('/api/v1/admin/hub/programme-candidates/verify-alias'), data);
  return response.data;
}

export async function rejectProgrammeCandidateGroup(data: { normalized_programme_name: string; campus_id: string; college_id: string; school_id: string }) {
  const response = await apiClient.post(apiUrl('/api/v1/admin/hub/programme-candidates/reject'), data);
  return response.data;
}

export async function fetchProgrammeCandidateSubmissions(normalized: string) {
  const response = await apiClient.get(apiUrl(`/api/v1/admin/hub/programme-candidates/${encodeURIComponent(normalized)}/submissions`));
  return response.data as { items: Array<Record<string, any>> };
}

export async function createProgrammeSubmission(data: { institution_id: string; campus_id: string; college_id: string; school_id: string; programme_name_other: string; source?: string; accepted_programme_id?: string | null; accepted_candidate_id?: number | null }) {
  const response = await apiClient.post(apiUrl('/api/v1/academics/programme-submissions'), data);
  return response.data;
}

export interface NotificationItem {
  id: number;
  user_id: string;
  title: string;
  message: string;
  notification_type: string;
  is_read: boolean | null;
  related_entity: string | null;
  related_entity_id: number | null;
  created_at: string | null;
}

export interface CommunityReportResult {
  paper: {
    id: number;
    report_count: number;
    is_hidden: boolean;
  };
}

export interface AdminOverview {
  stats: {
    total_papers: number;
    hidden_papers: number;
    verified_papers: number;
    total_reports: number;
    pending_reports: number;
    total_users: number;
    pending_role_requests: number;
  };
  top_contributors: UserProfile[];
  recent_reports: Array<{
    id: number;
    paper_id: number;
    user_id: string;
    reason: string;
    status: string | null;
    created_at: string | null;
  }>;
}

export interface AIStudyResponse {
  content: string;
  model: string;
  fallback_reason?: string | null;
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
}

export interface PersonalizedRecommendationsResponse {
  recently_viewed: Paper[];
  recommended: Paper[];
  top_departments: string[];
  top_paper_types: string[];
  top_course_codes: string[];
  data_source?: 'live' | 'cache';
}

const PAPERS_CACHE_KEY = 'ur-hud-paper-cache-v1';
const MY_PAPERS_CACHE_KEY = 'ur-hud-my-paper-cache-v1';
const DASHBOARD_CACHE_KEY = 'ur-hud-dashboard-cache-v1';
const PERSONALIZED_CACHE_KEY = 'ur-hud-personalized-cache-v1';
const PENDING_INTERACTION_EVENTS_KEY = 'ur-hud-pending-paper-events-v1';
const VIEW_THROTTLE_PREFIX = 'ur-hud-paper-view-throttle';
const RECOMMENDATIONS_UNAVAILABLE_SESSION_KEY = 'ur-hud-recommendations-unavailable';
const VIEW_TRACKING_UNAVAILABLE_SESSION_KEY = 'ur-hud-view-tracking-unavailable';

function offlineCacheKey(kind: 'paper' | 'solution', id: number) {
  return `/offline-docs/${kind}-${id}.pdf`;
}

function readCachedPaperList(): PaperListResponse | null {
  if (typeof window === 'undefined') return null;
  const raw = window.localStorage.getItem(PAPERS_CACHE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as PaperListResponse;
  } catch {
    return null;
  }
}

export function getCachedPaperListSnapshot(): PaperListResponse | null {
  return readCachedPaperList();
}

function writeCachedPaperList(data: PaperListResponse) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(PAPERS_CACHE_KEY, JSON.stringify(data));
}

function readCachedMyPaperList(): PaperListResponse | null {
  if (typeof window === 'undefined') return null;
  const raw = window.localStorage.getItem(MY_PAPERS_CACHE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as PaperListResponse;
  } catch {
    return null;
  }
}

function writeCachedMyPaperList(data: PaperListResponse) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(MY_PAPERS_CACHE_KEY, JSON.stringify(data));
}

function readCachedPersonalizedRecommendations(): PersonalizedRecommendationsResponse | null {
  if (typeof window === 'undefined') return null;
  const raw = window.localStorage.getItem(PERSONALIZED_CACHE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as PersonalizedRecommendationsResponse;
  } catch {
    return null;
  }
}

export function getCachedPersonalizedRecommendationsSnapshot(): PersonalizedRecommendationsResponse | null {
  return readCachedPersonalizedRecommendations();
}

function writeCachedPersonalizedRecommendations(data: PersonalizedRecommendationsResponse) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(PERSONALIZED_CACHE_KEY, JSON.stringify(data));
}

type PendingInteractionEvent = {
  paperId: number;
  type: 'view';
  createdAt: number;
};

function readPendingInteractionEvents(): PendingInteractionEvent[] {
  if (typeof window === 'undefined') return [];
  const raw = window.localStorage.getItem(PENDING_INTERACTION_EVENTS_KEY);
  if (!raw) return [];
  try {
    return JSON.parse(raw) as PendingInteractionEvent[];
  } catch {
    return [];
  }
}

function writePendingInteractionEvents(events: PendingInteractionEvent[]) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(PENDING_INTERACTION_EVENTS_KEY, JSON.stringify(events.slice(-20)));
}

function isSessionFeatureUnavailable(key: string) {
  if (typeof window === 'undefined') return false;
  return window.sessionStorage.getItem(key) === '1';
}

function markSessionFeatureUnavailable(key: string) {
  if (typeof window === 'undefined') return;
  window.sessionStorage.setItem(key, '1');
}

function paperField(item: Paper, key: string): unknown {
  return (item as unknown as Record<string, unknown>)[key];
}

export async function uploadFileObject(
  bucketName: string,
  objectKey: string,
  file: File,
  onProgress?: (percentage: number) => void
): Promise<string> {
  const formData = new FormData();
  formData.append('bucket_name', bucketName);
  formData.append('object_key', objectKey);
  formData.append('file', file);

  const response = await apiClient.post(apiUrl('/api/v1/storage/upload'), formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    onUploadProgress: (event) => {
      if (!event.total) return;
      onProgress?.(Math.min(100, Math.round((event.loaded / event.total) * 100)));
    },
  });

  const storedObjectKey = response.data?.object_key as string | undefined;
  if (!storedObjectKey) {
    throw new Error('Stored object key was not returned by the server');
  }

  return storedObjectKey;
}

export async function extractUploadPdfText(file: File): Promise<{ text: string; has_readable_text: boolean }> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiClient.post(apiUrl('/api/v1/storage/analyze-pdf'), formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data as { text: string; has_readable_text: boolean };
}

export async function getStorageDownloadUrl(
  bucketName: string,
  objectKey: string
): Promise<string | null> {
  if (/^https?:\/\//i.test(objectKey)) return objectKey;
  const cacheKey = `${bucketName}:${objectKey}`;
  const existing = storageDownloadUrls.get(cacheKey);
  if (existing) return existing;

  const request = apiClient
    .get(apiUrl('/api/v1/storage/download'), {
      params: {
        bucket_name: bucketName,
        object_key: objectKey,
      },
      responseType: 'blob',
    })
    .then((response) => URL.createObjectURL(response.data as Blob))
    .catch((error) => {
      storageDownloadUrls.delete(cacheKey);
      throw error;
    });

  storageDownloadUrls.set(cacheKey, request);
  return request;
}

export type DownloadProgress = { loaded: number; total?: number; percent?: number };
export async function downloadStorageObject(bucketName: string, objectKey: string, onProgress?: (progress: DownloadProgress) => void): Promise<string> {
  if (/^https?:\/\//i.test(objectKey)) return objectKey;
  const response = await apiClient.get(apiUrl('/api/v1/storage/download'), {
    params: { bucket_name: bucketName, object_key: objectKey }, responseType: 'blob',
    onDownloadProgress: (event) => onProgress?.({ loaded: event.loaded, total: event.total || undefined, percent: event.total ? Math.round((event.loaded / event.total) * 100) : undefined }),
  });
  return URL.createObjectURL(response.data as Blob);
}

// API helpers
export async function fetchAllPapers(params?: {
  query?: Record<string, unknown>;
  sort?: string;
  limit?: number;
  skip?: number;
}): Promise<PaperListResponse> {
  try {
    const response = await apiClient.get(apiUrl('/api/v1/entities/papers/all'), {
      params: {
        query: JSON.stringify(params?.query || {}),
        sort: params?.sort || '-created_at',
        limit: params?.limit || 50,
        skip: params?.skip || 0,
      },
    });
    const data = response.data as PaperListResponse;
    if (!params?.query || Object.keys(params.query).length === 0) {
      writeCachedPaperList(data);
    }
    return {
      ...data,
      data_source: 'live',
    };
  } catch (error) {
    const cached = readCachedPaperList();
    if (cached) {
      let items = [...cached.items];
      if (params?.query) {
        items = items.filter((item) =>
          Object.entries(params.query || {}).every(([key, value]) => paperField(item, key) === value)
        );
      }
      const sort = params?.sort || '-created_at';
      if (sort) {
        const reverse = sort.startsWith('-');
        const field = reverse ? sort.slice(1) : sort;
        items.sort((a, b) => {
          const left = paperField(a, field);
          const right = paperField(b, field);
          if (left === right) return 0;
          if (left == null) return reverse ? 1 : -1;
          if (right == null) return reverse ? -1 : 1;
          if (typeof left === 'number' && typeof right === 'number') {
            return reverse ? right - left : left - right;
          }
          return reverse
            ? String(right).localeCompare(String(left))
            : String(left).localeCompare(String(right));
        });
      }
      return {
        items: items.slice(params?.skip || 0, (params?.skip || 0) + (params?.limit || 50)),
        total: items.length,
        skip: params?.skip || 0,
        limit: params?.limit || 50,
        data_source: 'cache',
      };
    }
    throw error;
  }
}

export async function fetchAdminPapers(params?: {
  search?: string;
  page?: number;
  limit?: number;
  sort?: string;
}): Promise<PaperListResponse & { page: number; total_pages: number }> {
  const response = await apiClient.get(apiUrl('/api/v1/admin/hub/papers'), { params });
  return response.data as PaperListResponse & { page: number; total_pages: number };
}

export async function fetchPaperById(id: number): Promise<Paper> {
  const data = await fetchAllPapers({
    query: { id },
    limit: 1,
  });
  if (data.items.length === 0) throw new Error('Paper not found');
  return data.items[0];
}

export async function createPaper(data: Partial<Paper>): Promise<Paper> {
  const response = await apiClient.post(apiUrl('/api/v1/community/papers'), data);
  invalidateResourceCaches();
  return response.data as Paper;
}

export type ResourceSummary = {
  id: number; type: 'paper' | 'book'; title: string; created_at: string | null;
  uploader_id: string; downloads: number; visibility: string; verification_status: string | null;
  metadata: Record<string, any>;
};
export type DashboardData = {
  stats: { total_uploads: number; paper_count: number; book_count: number; total_downloads: number; verified_paper_count: number; average_downloads: number };
  uploaded_resources: ResourceSummary[];
  contribution: { upload_count: number; trust_score: number; role: string };
  leaderboard: UserProfile[];
};

export function getCachedDashboard(): DashboardData | null {
  if (typeof window === 'undefined') return null;
  try { return JSON.parse(window.localStorage.getItem(DASHBOARD_CACHE_KEY) || 'null') as DashboardData | null; } catch { return null; }
}

export async function fetchDashboard(): Promise<DashboardData> {
  const response = await apiClient.get(apiUrl('/api/v1/community/dashboard'));
  const data = response.data as DashboardData;
  if (typeof window !== 'undefined') window.localStorage.setItem(DASHBOARD_CACHE_KEY, JSON.stringify(data));
  return data;
}

export async function fetchPublicUserResources(userId: string): Promise<ResourceSummary[]> {
  const response = await apiClient.get(apiUrl(`/api/v1/community/profiles/${userId}/resources`));
  return (response.data?.items || []) as ResourceSummary[];
}

/** Called only after a committed resource mutation; listeners refresh in the background. */
export function invalidateResourceCaches() {
  if (typeof window === 'undefined') return;
  [PAPERS_CACHE_KEY, MY_PAPERS_CACHE_KEY, DASHBOARD_CACHE_KEY].forEach((key) => window.localStorage.removeItem(key));
  window.dispatchEvent(new Event('ur-resource-mutated'));
}

export async function fetchMyPapers(): Promise<PaperListResponse> {
  try {
    const response = await apiClient.get(apiUrl('/api/v1/entities/papers'), {
      params: {
        sort: '-created_at',
        limit: 100,
        skip: 0,
      },
    });
    const data = response.data as PaperListResponse;
    writeCachedMyPaperList(data);
    return {
      ...data,
      data_source: 'live',
    };
  } catch (error) {
    const cached = readCachedMyPaperList();
    if (cached) {
      return {
        ...cached,
        data_source: 'cache',
      };
    }
    throw error;
  }
}

export async function deleteMyPaper(paperId: number): Promise<void> {
  await apiClient.delete(apiUrl(`/api/v1/entities/papers/${paperId}`));
}

/** Uses the existing Paper endpoint; the server remains authoritative for Admin/CP access. */
export async function updatePaper(paperId: number, data: Partial<Pick<Paper, 'title' | 'course_code' | 'course_name' | 'college' | 'department' | 'year' | 'paper_type' | 'lecturer' | 'description' | 'file_key' | 'solution_key' | 'verification_status' | 'is_hidden'>>): Promise<Paper> {
  const response = await apiClient.put(apiUrl(`/api/v1/entities/papers/${paperId}`), data);
  return response.data as Paper;
}

export async function replacePaperFile(paperId: number, file: { file_key: string; file_name?: string; mime_type?: string; file_size?: number }): Promise<Paper> {
  return (await apiClient.post(apiUrl(`/api/v1/entities/papers/${paperId}/file`), file)).data as Paper;
}
export async function replacePaperCover(paperId: number, file: { file_key: string; file_name?: string; mime_type?: string; file_size?: number }): Promise<Paper> {
  return (await apiClient.post(apiUrl(`/api/v1/entities/papers/${paperId}/cover`), file)).data as Paper;
}
export async function replacePaperSolution(paperId: number, file: { file_key: string; file_name?: string; mime_type?: string; file_size?: number }): Promise<Paper> {
  return (await apiClient.post(apiUrl(`/api/v1/entities/papers/${paperId}/solution`), file)).data as Paper;
}
export async function removePaperSolution(paperId: number): Promise<void> {
  await apiClient.delete(apiUrl(`/api/v1/entities/papers/${paperId}/solution`));
}

export async function createComment(data: {
  paper_id?: number;
  book_id?: number;
  content: string;
  parent_id?: number;
}): Promise<Comment> {
  const resource = data.book_id ? `books/${data.book_id}` : `papers/${data.paper_id}`;
  const response = await apiClient.post(apiUrl(`/api/v1/community/${resource}/comments`), {
    content: data.content,
    parent_id: data.parent_id,
  });
  return response.data as Comment;
}

export async function fetchComments(paperId: number): Promise<{ items: Comment[]; total: number }> {
  const response = await apiClient.get(apiUrl('/api/v1/entities/comments/all'), {
      params: {
        query: JSON.stringify({ paper_id: paperId }),
        sort: '-created_at',
        limit: 100,
        skip: 0,
      },
    });
  return response.data as { items: Comment[]; total: number };
}

export async function fetchBookComments(bookId: number): Promise<{ items: Comment[]; total: number }> {
  const response = await apiClient.get(apiUrl('/api/v1/entities/comments/all'), {
      params: { query: JSON.stringify({ book_id: bookId }), sort: '-created_at', limit: 100, skip: 0 },
    });
  return response.data as { items: Comment[]; total: number };
}

export async function createSolution(data: {
  paper_id: number;
  content: string;
  file_key?: string;
}): Promise<Solution> {
  const response = await apiClient.post(apiUrl(`/api/v1/community/papers/${data.paper_id}/solutions`), {
    content: data.content,
  });
  return response.data as Solution;
}

export async function fetchSolutions(paperId: number): Promise<{ items: Solution[]; total: number }> {
  try {
    const response = await apiClient.get(apiUrl('/api/v1/entities/solutions/all'), {
      params: {
        query: JSON.stringify({ paper_id: paperId }),
        sort: '-upvotes',
        limit: 100,
        skip: 0,
      },
    });
    return response.data as { items: Solution[]; total: number };
  } catch {
    return { items: [], total: 0 };
  }
}

export async function createReport(data: {
  paper_id: number;
  reason: string;
}): Promise<CommunityReportResult> {
  const response = await apiClient.post(apiUrl(`/api/v1/community/papers/${data.paper_id}/report`), {
    reason: data.reason,
  });
  return response.data as CommunityReportResult;
}

export async function fetchUserProfile(): Promise<UserProfile | null> {
  try {
    const response = await apiClient.get(apiUrl('/api/v1/community/profile'));
    return response.data as UserProfile;
  } catch {
    return null;
  }
}

export async function fetchPublicUserProfile(userId: string): Promise<PublicUserProfile> {
  const response = await apiClient.get(apiUrl(`/api/v1/community/profiles/${encodeURIComponent(userId)}`));
  return response.data as PublicUserProfile;
}

export async function resolvePublicUserProfile(userId: string): Promise<{ profile: PublicUserProfile | null; imageUrl: string | null }> {
  const existing = resolvedPublicProfiles.get(userId);
  if (existing) return existing;

  const request = (async () => {
    try {
      const profile = await fetchPublicUserProfile(userId);
      if (!profile) return { profile: null, imageUrl: null };

      const key = profile.profile_picture_key;
      if (!key) return { profile, imageUrl: null };

      if (/^https?:\/\//i.test(key)) {
        return { profile, imageUrl: key };
      }

      try {
        const url = await getStorageDownloadUrl('profiles', key);
        return { profile, imageUrl: url };
      } catch {
        return { profile, imageUrl: null };
      }
    } catch {
      return { profile: null, imageUrl: null };
    }
  })();

  resolvedPublicProfiles.set(userId, request);
  return request;
}

export async function resolvePublicUserProfiles(userIds: string[]): Promise<Record<string, { profile: PublicUserProfile | null; imageUrl: string | null }>> {
  const results: Record<string, { profile: PublicUserProfile | null; imageUrl: string | null }> = {};
  await Promise.all(userIds.map(async (id) => {
    results[id] = await resolvePublicUserProfile(id);
  }));
  return results;
}

// Cache invalidation helpers for resolved public profiles.
export function clearResolvedPublicProfile(userId: string) {
  resolvedPublicProfiles.delete(userId);
}

export function clearAllResolvedPublicProfiles() {
  resolvedPublicProfiles.clear();
}

export async function createUserProfile(data: {
  display_name: string;
  role?: string;
}): Promise<UserProfile> {
  const response = await apiClient.post(apiUrl('/api/v1/entities/user_profiles'), {
    display_name: data.display_name,
    role: data.role || 'normal',
    trust_score: 0,
    upload_count: 0,
    download_count: 0,
  });
  return response.data as UserProfile;
}

export async function updateUserProfile(data: {
  display_name?: string;
  institution_type?: 'ur_student' | 'other_university';
  university_name?: string | null;
  ur_student_code?: string | null;
  profile_picture_key?: string | null;
  phone_number?: string | null;
  college_name?: string | null;
  department_name?: string | null;
  institution_id?: string | null;
  campus_id?: string | null;
  college_id?: string | null;
  school_id?: string | null;
  academic_department_id?: string | null;
  programme_id?: string | null;
  programme_name_other?: string | null;
  year_of_study?: string | null;
  bio?: string | null;
}): Promise<UserProfile> {
  const response = await apiClient.patch(apiUrl('/api/v1/community/profile'), data);
  return response.data as UserProfile;
}

export async function upvoteSolution(solutionId: number): Promise<Solution> {
  const response = await apiClient.post(apiUrl(`/api/v1/community/solutions/${solutionId}/upvote`));
  return response.data as Solution;
}

export async function upvoteComment(commentId: number): Promise<Comment> {
  const response = await apiClient.post(apiUrl(`/api/v1/community/comments/${commentId}/upvote`));
  return response.data as Comment;
}

async function flushPendingPaperInteractionEvents(): Promise<void> {
  const token = getStoredAuthToken();
  if (!token) {
    writePendingInteractionEvents([]);
    return;
  }

  if (isSessionFeatureUnavailable(VIEW_TRACKING_UNAVAILABLE_SESSION_KEY)) {
    writePendingInteractionEvents([]);
    return;
  }

  const pendingEvents = readPendingInteractionEvents();
  if (pendingEvents.length === 0) {
    return;
  }

  const remaining: PendingInteractionEvent[] = [];
  for (const event of pendingEvents) {
    try {
      if (event.type === 'view') {
        await apiClient.post(apiUrl(`/api/v1/community/papers/${event.paperId}/record-view`));
      }
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        markSessionFeatureUnavailable(VIEW_TRACKING_UNAVAILABLE_SESSION_KEY);
        writePendingInteractionEvents([]);
        return;
      }
      remaining.push(event);
    }
  }

  writePendingInteractionEvents(remaining);
}

export async function trackPaperView(paperId: number): Promise<void> {
  const token = getStoredAuthToken();
  if (!token || typeof window === 'undefined' || isSessionFeatureUnavailable(VIEW_TRACKING_UNAVAILABLE_SESSION_KEY)) {
    return;
  }

  const throttleKey = `${VIEW_THROTTLE_PREFIX}:${paperId}`;
  const lastTrackedAt = Number(window.sessionStorage.getItem(throttleKey) || '0');
  const now = Date.now();
  if (lastTrackedAt && now - lastTrackedAt < 10 * 60 * 1000) {
    return;
  }

  window.sessionStorage.setItem(throttleKey, String(now));
  const pendingEvents = readPendingInteractionEvents();
  pendingEvents.push({ paperId, type: 'view', createdAt: now });
  writePendingInteractionEvents(pendingEvents);

  try {
    await flushPendingPaperInteractionEvents();
  } catch {
    // Keep the event queued for a later retry. View tracking must never block the page.
  }
}

export async function recordPaperDownload(paperId: number): Promise<{ download_count: number }> {
  const response = await apiClient.post(apiUrl(`/api/v1/community/papers/${paperId}/record-download`));
  return response.data as { download_count: number };
}

export async function fetchPersonalizedRecommendations(): Promise<PersonalizedRecommendationsResponse | null> {
  if (isSessionFeatureUnavailable(RECOMMENDATIONS_UNAVAILABLE_SESSION_KEY)) {
    const cached = readCachedPersonalizedRecommendations();
    return cached ? { ...cached, data_source: 'cache' } : null;
  }

  try {
    await flushPendingPaperInteractionEvents();
    const response = await apiClient.get(apiUrl('/api/v1/community/papers/recommendations'));
    const data = {
      ...(response.data as PersonalizedRecommendationsResponse),
      data_source: 'live' as const,
    };
    writeCachedPersonalizedRecommendations(data);
    return data;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      markSessionFeatureUnavailable(RECOMMENDATIONS_UNAVAILABLE_SESSION_KEY);
      return readCachedPersonalizedRecommendations()
        ? { ...(readCachedPersonalizedRecommendations() as PersonalizedRecommendationsResponse), data_source: 'cache' }
        : null;
    }

    if (axios.isAxiosError(error) && error.response?.status === 401) {
      return readCachedPersonalizedRecommendations()
        ? { ...(readCachedPersonalizedRecommendations() as PersonalizedRecommendationsResponse), data_source: 'cache' }
        : null;
    }

    const cached = readCachedPersonalizedRecommendations();
    if (cached) {
      return { ...cached, data_source: 'cache' };
    }
    return null;
  }
}

export async function fetchLeaderboard(): Promise<UserProfile[]> {
  const response = await apiClient.get(apiUrl('/api/v1/community/leaderboard'));
  return response.data.items as UserProfile[];
}

export async function fetchAdminOverview(): Promise<AdminOverview> {
  const response = await apiClient.get(apiUrl('/api/v1/admin/hub/overview'));
  return response.data as AdminOverview;
}

export interface SiteAccessSettings {
  maintenance_mode: boolean;
  maintenance_message: string;
  upload_access_mode: 'nobody' | 'authenticated' | 'selected_roles';
  upload_roles: string[];
  allowed_resource_types: string[];
  heartbeat_enabled: boolean;
  heartbeat_min_weekly_checks: number;
  heartbeat_max_weekly_checks: number;
  heartbeat_retry_delay_hours: number;
  heartbeat_max_retry_attempts: number;
  heartbeat_retry_enabled: boolean;
  heartbeat_retry_jitter_minutes: number;
  heartbeat_run_on_startup: boolean;
  heartbeat_notify_admin?: boolean;
  heartbeat?: HeartbeatStatus;
}

export interface PublicSiteAccessSettings {
  maintenance_mode: boolean;
  maintenance_message: string;
  upload_access_mode: 'nobody' | 'authenticated' | 'selected_roles';
  upload_roles: string[];
  allowed_resource_types: string[];
}

export interface HeartbeatStatus { enabled: boolean; scheduler_running: boolean; last_attempt_at?: string; last_success_at?: string; last_failure_at?: string; next_scheduled_at?: string; next_retry_at?: string; total_attempts: number; total_successes: number; total_failures: number; consecutive_failures: number; retry_attempts: number; status: string; activity_message?: string; }

export async function fetchSiteAccessSettings(): Promise<SiteAccessSettings> {
  const response = await apiClient.get(apiUrl('/api/v1/admin/settings/site-access'));
  return response.data as SiteAccessSettings;
}

export async function fetchPublicSiteAccessSettings(): Promise<PublicSiteAccessSettings> {
  const response = await apiClient.get(apiUrl('/health/site-access'));
  return response.data as PublicSiteAccessSettings;
}

export async function saveSiteAccessSettings(settings: Partial<SiteAccessSettings>): Promise<SiteAccessSettings> {
  const response = await apiClient.put(apiUrl('/api/v1/admin/settings/site-access'), settings);
  return response.data as SiteAccessSettings;
}

export async function fetchHeartbeatStatus(): Promise<HeartbeatStatus> {
  return (await apiClient.get(apiUrl('/api/v1/admin/settings/heartbeat'))).data as HeartbeatStatus;
}

export function heartbeatStreamUrl(): string {
  return apiUrl('/api/v1/admin/settings/heartbeat/stream');
}

export async function runHeartbeatNow(): Promise<{ executed: boolean; success: boolean; reason: string; heartbeat: HeartbeatStatus }> {
  return (await apiClient.post(apiUrl('/api/v1/admin/settings/heartbeat/run'))).data;
}

export async function transferSuperAdmin(replacementProfileId: number): Promise<void> {
  await apiClient.post(apiUrl('/api/v1/admin/hub/super-admin/transfer'), { replacement_profile_id: replacementProfileId, confirm: true });
}

export async function fetchAdminUsers(params?: { search?: string; role?: string; status?: string; page?: number; limit?: number; sort?: string }): Promise<{ items: UserProfile[]; total: number; page: number; limit: number; total_pages: number }> {
  const response = await apiClient.get(apiUrl('/api/v1/admin/hub/users'), {
    params,
  });
  return response.data;
}

export async function fetchAdminUserResources(profileId: number): Promise<{ papers: Array<Pick<Paper, 'id' | 'title' | 'course_code' | 'course_name' | 'year' | 'paper_type' | 'verification_status' | 'is_hidden' | 'created_at'>>; books: Array<{ id: number; title: string; language?: string | null; status: string; visibility: string; created_at?: string | null; file_name?: string | null; file_size?: number | null }>; activity: Array<{ kind: string; title: string; action: string; created_at?: string | null }> }> {
  const response = await apiClient.get(apiUrl(`/api/v1/admin/hub/users/${profileId}/resources`));
  return response.data;
}

export async function fetchAdminRoleRequests(): Promise<UserProfile[]> {
  try {
    const response = await apiClient.get(apiUrl('/api/v1/admin/hub/role-requests'));
    return response.data.items as UserProfile[];
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      console.warn('Role request endpoint is not available on the current backend deployment yet.');
      return [];
    }
    throw error;
  }
}

export async function moderatePaper(
  paperId: number,
  data: { verification_status?: string; is_hidden?: boolean }
): Promise<Paper> {
  const response = await apiClient.patch(apiUrl(`/api/v1/admin/hub/papers/${paperId}`), data);
  return response.data as Paper;
}

export async function updateAdminUser(
  profileId: number,
  data: {
    email?: string;
    display_name?: string;
    role?: string;
    trust_score?: number;
    account_status?: string;
    ur_verification_status?: string;
    institution_type?: 'ur_student' | 'other_university';
    university_name?: string | null;
    ur_student_code?: string | null;
    profile_picture_key?: string | null;
    phone_number?: string | null;
    college_name?: string | null;
    department_name?: string | null;
    year_of_study?: string | null;
    bio?: string | null;
    suspension_reason?: string;
    suspended_until?: string | null;
  }
): Promise<UserProfile> {
  const response = await apiClient.patch(apiUrl(`/api/v1/admin/hub/users/${profileId}`), data);
  return response.data as UserProfile;
}

export async function reviewAdminRoleRequest(
  profileId: number,
  data: { action: 'approve' | 'reject' }
): Promise<UserProfile> {
  const response = await apiClient.post(apiUrl(`/api/v1/admin/hub/role-requests/${profileId}/review`), data);
  return response.data as UserProfile;
}

export async function deleteAdminUser(profileId: number): Promise<void> {
  await apiClient.delete(apiUrl(`/api/v1/admin/hub/users/${profileId}`));
}

export async function updateAdminReport(
  reportId: number,
  data: { status: string; hide_paper?: boolean; verification_status?: string }
): Promise<void> {
  await apiClient.patch(apiUrl(`/api/v1/admin/hub/reports/${reportId}`), data);
}

export async function fetchNotifications(): Promise<NotificationItem[]> {
  const response = await apiClient.get(apiUrl('/api/v1/notifications'));
  return response.data.items as NotificationItem[];
}

export async function markNotificationRead(notificationId: number, isRead = true): Promise<NotificationItem> {
  const response = await apiClient.patch(apiUrl(`/api/v1/notifications/${notificationId}`), {
    is_read: isRead,
  });
  return response.data as NotificationItem;
}

export async function markAllNotificationsRead(): Promise<{ updated: number }> {
  const response = await apiClient.post(apiUrl('/api/v1/notifications/read-all'));
  return response.data as { updated: number };
}

export async function runStudyAI(paperId: number, action: 'explain' | 'summarize' | 'question', question?: string): Promise<AIStudyResponse> {
  const response = await apiClient.post(apiUrl(`/api/v1/study-ai/papers/${paperId}`), { action, question });
  return response.data as AIStudyResponse;
}

export async function saveDocumentOffline(sourceUrl: string, kind: 'paper' | 'solution', id: number): Promise<string> {
  if (!('caches' in window)) {
    throw new Error('Offline cache is not supported in this browser');
  }
  const cache = await caches.open('ur-hud-offline-documents');
  const response = await fetch(sourceUrl, { mode: 'cors' });
  if (!response.ok) {
    throw new Error('Failed to fetch document for offline storage');
  }
  const key = offlineCacheKey(kind, id);
  await cache.put(key, response.clone());
  return key;
}

export async function getOfflineDocumentUrl(kind: 'paper' | 'solution', id: number): Promise<string | null> {
  if (!('caches' in window)) {
    return null;
  }
  const cache = await caches.open('ur-hud-offline-documents');
  const key = offlineCacheKey(kind, id);
  const cached = await cache.match(key);
  return cached ? key : null;
}
