import { getAPIBaseURL } from './config';
import { apiClient, invalidateResourceCaches } from './client';

export type BookStatus = 'draft' | 'active' | 'inactive' | 'archived';
export type BookFile = { key: string; original_filename?: string | null; mime_type?: string | null; size?: number | null };
export type Book = {
  id: number; title: string; description?: string | null; isbn?: string | null; edition?: string | null;
  publication_year?: number | null; year_of_study?: string | null; semester?: string | null; language?: string | null; publisher?: string | null; category?: string | null; subject?: string | null;
  status: BookStatus; visibility: 'public' | 'private'; uploaded_by: string; uploader_name?: string | null; uploader_role?: string | null;
  download_count?: number | null;
  created_at: string; updated_at: string; management_deadline: string; can_manage: boolean;
  authors: string[]; course_ids: number[]; courses?: Course[]; modules?: Module[]; cover_key?: string | null; file_key?: string | null; file_name?: string | null;
};
export type BookDraft = Omit<Partial<Book>, 'authors' | 'course_ids' | 'status'> & { title: string; authors: string[]; course_ids: number[]; module_ids?: number[]; status: BookStatus; file?: BookFile; cover?: BookFile };
export type Module = { id: number; name: string; code?: string | null; description?: string | null; course_id?: number | null; existing?: boolean };
export type Course = { id: number; code?: string | null; name: string; description?: string | null; existing?: boolean };

const url = (path: string) => `${getAPIBaseURL()}${path}`;

/** UI-only convenience. Server authorization remains authoritative. */
export function canManageBook(user: { id: string; role: string } | null | undefined, book: Pick<Book, 'uploaded_by' | 'created_at'>): boolean {
  if (!user) return false;
  const permissions = (user as { permissions?: string[] }).permissions || [];
  if (permissions.includes('books.edit')) return true;
  return permissions.includes('books.own.manage') && user.id === book.uploaded_by && Date.now() <= new Date(book.created_at).getTime() + 48 * 60 * 60 * 1000;
}

export async function fetchBooks(params?: Record<string, string | boolean | undefined>) {
  return (await apiClient.get(url('/api/v1/books'), { params })).data as { items: Book[]; total: number };
}
export async function fetchBookById(id: number) { return (await apiClient.get(url(`/api/v1/books/${id}`))).data as Book; }
export async function recordBookDownload(id: number) { return (await apiClient.post(url(`/api/v1/books/${id}/record-download`))).data as { download_count: number }; }
export async function fetchBookStats() { return (await apiClient.get(url('/api/v1/books/stats'))).data as Record<string, number>; }
export async function createBook(data: BookDraft) {
  const book = (await apiClient.post(url('/api/v1/books'), data)).data as Book;
  invalidateResourceCaches();
  return book;
}
export async function updateBook(id: number, data: Partial<BookDraft>) { return (await apiClient.put(url(`/api/v1/books/${id}`), data)).data as Book; }
export async function deleteBook(id: number) { await apiClient.delete(url(`/api/v1/books/${id}`)); invalidateResourceCaches(); }
export async function setBookStatus(id: number, status: BookStatus) { return (await apiClient.patch(url(`/api/v1/books/${id}/status`), { status })).data as Book; }
export async function updateBookAuthors(id: number, authors: string[]) { return (await apiClient.patch(url(`/api/v1/books/${id}/authors`), { authors })).data as Book; }
export async function updateBookCourses(id: number, course_ids: number[]) { return (await apiClient.patch(url(`/api/v1/books/${id}/courses`), { course_ids })).data as Book; }
export async function updateBookModules(id: number, module_ids: number[]) { return (await apiClient.patch(url(`/api/v1/books/${id}/modules`), { module_ids })).data as Book; }
export async function fetchBookActivity(id: number) { return (await apiClient.get(url(`/api/v1/books/${id}/activity`))).data as { items: Array<{ id: number; action: string; detail?: string | null; created_at?: string | null; actor_id?: string | null }> }; }
export async function replaceBookFile(id: number, file: BookFile) { return (await apiClient.post(url(`/api/v1/books/${id}/file`), file)).data as Book; }
export async function replaceBookCover(id: number, file: BookFile) { return (await apiClient.post(url(`/api/v1/books/${id}/cover`), file)).data as Book; }
export async function fetchModules(query?: string) { return (await apiClient.get(url('/api/v1/modules/search'), { params: { q: query || 'a' } })).data as { items: Module[] }; }
export async function createModule(data: { name: string; code?: string; description?: string; course_id?: number }) { return (await apiClient.post(url('/api/v1/modules'), data)).data as Module; }
export async function searchCourses(q: string) { return (await apiClient.get(url('/api/v1/courses/search'), { params: { q } })).data as { items: Course[]; total: number }; }
export async function createCourse(data: { name: string; code?: string; description?: string }) { return (await apiClient.post(url('/api/v1/courses'), data)).data as Course; }
