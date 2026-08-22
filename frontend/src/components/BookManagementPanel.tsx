import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { BookOpen, Clock, Eye, Lock, Search, Trash2 } from 'lucide-react';
import { showMessage, toast } from '@/lib/messages';
import { normalizeApiError } from '@/lib/api-errors';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { deleteBook, fetchBookActivity, fetchBooks, setBookStatus, updateBook, type Book, type BookStatus } from '@/lib/books';
import AdminDetailDialog from '@/components/AdminDetailDialog';
import BookManagementEditor from '@/components/BookManagementEditor';

type Props = { mode: 'admin' | 'cp'; userId: string };

export default function BookManagementPanel({ mode, userId }: Props) {
  const [books, setBooks] = useState<Book[]>([]);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('all');
  const [visibility, setVisibility] = useState('all');
  const [loading, setLoading] = useState(true);
  const [selectedBook, setSelectedBook] = useState<Book | null>(null);
  const [activity, setActivity] = useState<Array<{ id: number; action: string; detail?: string | null; created_at?: string | null }>>([]);

  const load = async () => {
    setLoading(true);
    try {
      const data = await fetchBooks(mode === 'admin' ? {} : { uploaded_by: userId });
      setBooks(data.items);
    } catch (error) {
      toast.error(normalizeApiError(error).message || 'Unable to load book management');
    } finally { setLoading(false); }
  };

  useEffect(() => { void load(); }, [mode, userId]);

  const visible = useMemo(() => books.filter((book) => {
    const query = search.toLowerCase();
    return (!query || [book.title, book.authors.join(' '), book.uploader_name, book.language].filter(Boolean).some((value) => String(value).toLowerCase().includes(query)))
      && (status === 'all' || book.status === status)
      && (visibility === 'all' || book.visibility === visibility);
  }), [books, search, status, visibility]);

  const replace = (next: Book) => {
    setBooks((items) => items.map((item) => item.id === next.id ? next : item));
    setSelectedBook((current) => current?.id === next.id ? next : current);
  };
  const operationError = (error: unknown, fallback: string) => toast.error(normalizeApiError(error).message || fallback);
  const changeStatus = async (book: Book, next: BookStatus) => { try { replace(await setBookStatus(book.id, next)); toast.success(`Book marked ${next}`); } catch (error) { operationError(error, 'Status update was denied'); } };
  const changeVisibility = async (book: Book) => { try { replace(await updateBook(book.id, { visibility: book.visibility === 'public' ? 'private' : 'public' })); toast.success('Visibility updated'); } catch (error) { operationError(error, 'Visibility update was denied'); } };
  const remove = async (book: Book) => { try { await deleteBook(book.id); setBooks((items) => items.filter((item) => item.id !== book.id)); setSelectedBook(null); toast.success('Book permanently deleted'); } catch (error) { operationError(error, 'Delete was denied'); return false; } };
  const openBook = (book: Book) => { setSelectedBook(book); setActivity([]); void fetchBookActivity(book.id).then((result) => setActivity(result.items)).catch(() => undefined); };
  const confirmDelete = (book: Book) => showMessage({ type: 'confirmation', title: 'Delete Book?', message: 'This permanently deletes the Book and its stored files.', actions: [{ label: 'Cancel', variant: 'outline', onClick: () => undefined }, { label: 'Delete', loadingLabel: 'Deleting...', variant: 'destructive', onClick: () => remove(book) }] });

  return <>
    <Card className="theme-panel"><CardContent className="p-5">
      <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-end md:justify-between"><div><h2 className="theme-title text-xl font-bold">{mode === 'admin' ? 'Book Management' : 'My Books'}</h2><p className="theme-muted mt-1 text-sm">{mode === 'admin' ? 'Manage every Book, including private, inactive, draft, and deleted records.' : 'Only your uploads are shown. The server enforces the 48-hour management window.'}</p></div><Button variant="outline" onClick={() => void load()}>Refresh</Button></div>
      <div className="mb-5 grid gap-3 md:grid-cols-3"><div className="relative"><Search className="theme-muted absolute left-3 top-3 h-4 w-4" /><Input className="pl-9" placeholder="Search books or authors" value={search} onChange={(event) => setSearch(event.target.value)} /></div><Select value={status} onValueChange={setStatus}><SelectTrigger><SelectValue placeholder="All statuses" /></SelectTrigger><SelectContent><SelectItem value="all">All statuses</SelectItem><SelectItem value="draft">Draft</SelectItem><SelectItem value="active">Active</SelectItem><SelectItem value="inactive">Inactive</SelectItem><SelectItem value="deleted">Deleted</SelectItem></SelectContent></Select><Select value={visibility} onValueChange={setVisibility}><SelectTrigger><SelectValue placeholder="All visibility" /></SelectTrigger><SelectContent><SelectItem value="all">All visibility</SelectItem><SelectItem value="public">Public</SelectItem><SelectItem value="private">Private</SelectItem></SelectContent></Select></div>
      {loading ? <div className="grid grid-cols-[repeat(auto-fit,minmax(250px,1fr))] gap-4">{[1, 2, 3].map((item) => <div key={item} className="h-52 animate-pulse rounded-xl bg-muted" />)}</div> : !visible.length ? <p className="theme-muted py-10 text-center">No Books match these filters.</p> : <div className="grid grid-cols-[repeat(auto-fit,minmax(250px,1fr))] gap-4">{visible.map((book) => <Card key={book.id} className="theme-soft-panel"><CardContent className="flex h-full flex-col p-4"><div className="theme-panel mb-4 flex h-20 w-14 items-center justify-center overflow-hidden rounded"><BookOpen className="h-7 w-7 text-muted-foreground" /></div><div className="flex flex-wrap items-center gap-2"><p className="theme-title line-clamp-2 font-semibold">{book.title}</p><Badge variant="outline">{book.status}</Badge><Badge variant="outline">{book.visibility}</Badge></div><p className="theme-muted mt-2 line-clamp-2 text-sm">{book.authors.join(', ') || 'No author'} · {book.language || 'Language unavailable'}</p><p className="theme-muted mt-1 line-clamp-2 text-xs">{book.courses?.map((course) => course.code || course.name).join(', ') || 'No course'} · {book.modules?.map((module) => module.code || module.name).join(', ') || 'No module'}</p><p className="theme-muted mt-3 text-xs">Uploaded by {book.uploader_name || book.uploaded_by}</p><Button className="mt-auto pt-4" variant="outline" onClick={() => openBook(book)}><Eye className="mr-1 h-4 w-4" />View Full Book</Button></CardContent></Card>)}</div>}
      {mode === 'cp' && <p className="theme-muted mt-4 flex items-center gap-2 text-xs"><Clock className="h-3.5 w-3.5" />The API is authoritative: disabled controls are informational and server permission checks still apply.</p>}
    </CardContent></Card>
    <AdminDetailDialog open={Boolean(selectedBook)} onOpenChange={(open) => !open && setSelectedBook(null)} title={selectedBook?.title || 'Book management'} description="Review metadata and use the existing server-authorized management actions.">
      {selectedBook && <div className="space-y-5"><BookManagementEditor book={selectedBook} canManage={selectedBook.can_manage || mode === 'admin'} onUpdated={replace} /><div className="grid gap-3 text-sm sm:grid-cols-2"><p><span className="theme-muted">Uploader</span><br />{selectedBook.uploader_name || selectedBook.uploaded_by}</p><p><span className="theme-muted">Uploaded</span><br />{selectedBook.created_at || 'Not provided'}</p><p><span className="theme-muted">Updated</span><br />{selectedBook.updated_at || 'Not provided'}</p><p><span className="theme-muted">File</span><br />{selectedBook.file_name || 'Not provided'}</p><p><span className="theme-muted">Activity</span><br />{activity.length ? activity.map((item) => item.action).join(', ') : 'No activity recorded'}</p></div><div className="flex flex-wrap gap-2"><Button variant="outline" asChild><Link to={`/book/${selectedBook.id}`}><Eye className="mr-1 h-4 w-4" />Open public reader</Link></Button><Button variant="outline" disabled={!selectedBook.can_manage && mode !== 'admin'} onClick={() => void changeStatus(selectedBook, selectedBook.status === 'active' ? 'inactive' : 'active')}>{selectedBook.status === 'active' ? 'Deactivate' : 'Activate'}</Button><Button variant="outline" disabled={!selectedBook.can_manage && mode !== 'admin'} onClick={() => void changeVisibility(selectedBook)}><Lock className="mr-1 h-4 w-4" />Make {selectedBook.visibility === 'public' ? 'private' : 'public'}</Button><Button variant="destructive" disabled={!selectedBook.can_manage && mode !== 'admin'} onClick={() => confirmDelete(selectedBook)}><Trash2 className="mr-1 h-4 w-4" />Delete</Button></div></div>}
    </AdminDetailDialog>
  </>;
}
