import axios from 'axios';
import { getAPIBaseURL } from './config';
import { getStoredAuthToken } from './auth';

export type BookStatus = 'draft' | 'active' | 'inactive' | 'archived';
export type BookFile = { key: string; original_filename?: string | null; mime_type?: string | null; size?: number | null };
export type Book = {
  id: number; title: string; description?: string | null; isbn?: string | null; edition?: string | null;
  publication_year?: number | null; language?: string | null; publisher?: string | null; category?: string | null; subject?: string | null;
  status: BookStatus; visibility: 'public' | 'private'; uploaded_by: string; uploader_name?: string | null; uploader_role?: string | null;
  download_count?: number | null;
  created_at: string; updated_at: string; management_deadline: string; can_manage: boolean; deleted_at?: string | null;
  authors: string[]; course_ids: number[]; modules?: Module[]; cover_key?: string | null; file_key?: string | null; file_name?: string | null;
};
export type BookDraft = Omit<Partial<Book>, 'authors' | 'course_ids' | 'status'> & { title: string; authors: string[]; course_ids: number[]; module_ids?: number[]; status: BookStatus; file?: BookFile; cover?: BookFile };
export type Module = { id: number; name: string; code?: string | null; description?: string | null; course_id?: number | null; existing?: boolean };
export type Course = { id: number; code?: string | null; name: string; description?: string | null; existing?: boolean };

const client = axios.create();
client.interceptors.request.use((config) => {
  const token = getStoredAuthToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
const url = (path: string) => `${getAPIBaseURL()}${path}`;

/** UI-only convenience. Server authorization remains authoritative. */
export function canManageBook(user: { id: string; role: string } | null | undefined, book: Pick<Book, 'uploaded_by' | 'created_at'>): boolean {
  if (!user) return false;
  if (user.role === 'admin') return true;
  return user.role === 'cp' && user.id === book.uploaded_by && Date.now() <= new Date(book.created_at).getTime() + 48 * 60 * 60 * 1000;
}

export async function fetchBooks(params?: Record<string, string | boolean | undefined>) {
  return (await client.get(url('/api/v1/books'), { params })).data as { items: Book[]; total: number };
}
export async function fetchBookStats() { return (await client.get(url('/api/v1/books/stats'))).data as Record<string, number>; }
export async function createBook(data: BookDraft) { return (await client.post(url('/api/v1/books'), data)).data as Book; }
export async function updateBook(id: number, data: Partial<BookDraft>) { return (await client.put(url(`/api/v1/books/${id}`), data)).data as Book; }
export async function deleteBook(id: number) { await client.delete(url(`/api/v1/books/${id}`)); }
export async function setBookStatus(id: number, status: BookStatus) { return (await client.patch(url(`/api/v1/books/${id}/status`), { status })).data as Book; }
export async function fetchModules(query?: string) { return (await client.get(url('/api/v1/modules/search'), { params: { q: query || 'a' } })).data as { items: Module[] }; }
export async function createModule(data: { name: string; code?: string; description?: string; course_id?: number }) { return (await client.post(url('/api/v1/modules'), data)).data as Module; }
export async function searchCourses(q: string) { return (await client.get(url('/api/v1/courses/search'), { params: { q } })).data as { items: Course[]; total: number }; }
export async function createCourse(data: { name: string; code?: string; description?: string }) { return (await client.post(url('/api/v1/courses'), data)).data as Course; }
