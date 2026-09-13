import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, BookOpen, ChevronUp, Clock, Download, FileText, MessageSquare, Reply, Send, User, ZoomIn, ZoomOut } from 'lucide-react';
import { toast } from '@/lib/messages';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { useAuth } from '../contexts/AuthContext';
import AvatarFallback from '../components/AvatarFallback';
import DocumentPreview from '../components/DocumentPreview';
import DocumentLoadingProgress from '../components/DocumentLoadingProgress';
import DocumentCoverPreview from '../components/DocumentCoverPreview';
import { downloadStorageObject, fetchBookComments, createComment, getStorageDownloadUrl, resolvePublicUserProfiles, upvoteComment, type Comment } from '../lib/client';
import { fetchBookById, recordBookDownload, type Book } from '../lib/books';

export default function BookDetails() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [book, setBook] = useState<Book | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [commentsError, setCommentsError] = useState(false);
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [coverUrl, setCoverUrl] = useState<string | null>(null);
  const [bookLoading, setBookLoading] = useState(true);
  const [fileLoading, setFileLoading] = useState(false);
  const [fileProgress, setFileProgress] = useState<{ loaded: number; total?: number; percent?: number } | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [coverFailed, setCoverFailed] = useState(false);
  const [newComment, setNewComment] = useState('');
  const [replyTarget, setReplyTarget] = useState<number | null>(null);
  const [replyDraft, setReplyDraft] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [profiles, setProfiles] = useState<Record<string, { display_name?: string | null; imageUrl?: string | null }>>({});

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setBookLoading(true); setBook(null); setFileUrl(null); setCoverUrl(null); setCoverFailed(false);
    void fetchBookById(Number(id)).then((bookData) => {
      if (cancelled) return;
      setBook(bookData); setBookLoading(false);
      if (bookData.cover_key) void getStorageDownloadUrl('books', bookData.cover_key).then((url) => !cancelled && setCoverUrl(url)).catch(() => !cancelled && setCoverFailed(true));
      if (bookData.file_key) void loadBookDocument(bookData.file_key, cancelled);
    }).catch(() => { if (!cancelled) { setBook(null); setBookLoading(false); toast.error('Failed to load book details'); } });
    void fetchBookComments(Number(id)).then((data) => { if (!cancelled) { setComments(data.items); setCommentsError(false); } }).catch(() => { if (!cancelled) { setComments([]); setCommentsError(true); } });
    return () => { cancelled = true; };
  }, [id]);

  const [fileHttpErrorStatus, setFileHttpErrorStatus] = useState<number | null>(null);

  const loadBookDocument = async (key: string, cancelled = false) => {
    setFileLoading(true); setFileError(null); setFileHttpErrorStatus(null); setFileProgress({ loaded: 0 });
    try {
      const url = await downloadStorageObject('books', key, (progress) => !cancelled && setFileProgress(progress));
      if (!cancelled) setFileUrl(url);
    } catch (err: any) {
      if (!cancelled) {
        const status = err?.response?.status || null;
        setFileHttpErrorStatus(status);
        if (status === 404) {
          setFileError('This file could not be found in storage.');
        } else if (status === 403) {
          setFileError("You don't have permission to access this document.");
        } else {
          setFileError('The book file could not be retrieved from storage.');
        }
      }
    } finally {
      if (!cancelled) setFileLoading(false);
    }
  };

  useEffect(() => {
    const ids = Array.from(new Set(comments.map((comment) => comment.user_id).concat(book?.uploaded_by || [])));
    if (!ids.length) return;
    void resolvePublicUserProfiles(ids).then((resolved) => {
      const next: Record<string, { display_name?: string | null; imageUrl?: string | null }> = {};
      ids.forEach((userId) => { next[userId] = { display_name: resolved[userId]?.profile?.display_name || null, imageUrl: resolved[userId]?.imageUrl || null }; });
      setProfiles(next);
    }).catch(() => undefined);
  }, [comments, book?.uploaded_by]);

  const submitComment = async (content: string, parentId?: number) => {
    if (!book || !user || !content.trim()) return;
    try {
      setSubmitting(true);
      const comment = await createComment({ book_id: book.id, content: content.trim(), parent_id: parentId });
      setComments((previous) => [comment, ...previous]);
      if (parentId) { setReplyDraft(''); setReplyTarget(null); } else setNewComment('');
      toast.success(parentId ? 'Reply posted' : 'Comment posted');
    } catch { toast.error(parentId ? 'Failed to post reply' : 'Failed to post comment'); }
    finally { setSubmitting(false); }
  };

  const handleDownload = async () => {
    if (!book?.file_key || !fileUrl) return;
    window.open(fileUrl, '_blank');
    try { const result = await recordBookDownload(book.id); setBook((previous) => previous ? { ...previous, download_count: result.download_count } : previous); } catch { /* opening the file already succeeded */ }
  };

  if (!book && !bookLoading) return <div className="mx-auto max-w-4xl px-4 py-16 text-center"><h2 className="theme-title mb-4 text-2xl font-bold">Book Not Found</h2><Button onClick={() => navigate('/resources?resource=book')}>Browse Resources</Button></div>;
  const viewBook = book;

  const roots = comments.filter((comment) => !comment.parent_id).sort((a, b) => (b.upvotes || 0) - (a.upvotes || 0));
  const replies = (parentId: number) => comments.filter((comment) => comment.parent_id === parentId).sort((a, b) => (a.created_at || '').localeCompare(b.created_at || ''));
  const displayName = viewBook ? profiles[viewBook.uploaded_by]?.display_name || viewBook.uploader_name || (viewBook.uploaded_by ? `Contributor ${viewBook.uploaded_by}` : 'Academic Contributor') : 'Loading uploader';

  return <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6 lg:px-8">
    <Button variant="ghost" onClick={() => navigate(-1)} className="theme-muted mb-6"><ArrowLeft className="mr-2 h-4 w-4" />Back</Button>
    <Card className="theme-panel mb-6"><CardContent className="p-6">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Badge variant="outline" className="border-primary text-primary"><BookOpen className="mr-1 h-3 w-3" />BOOK</Badge>
        <Badge variant="outline">{viewBook?.language || 'Opening Book...'}</Badge>
        {viewBook?.edition && <Badge variant="outline">{viewBook.edition}</Badge>}
        {viewBook?.year_of_study && (
          <Badge variant="outline" className="bg-primary/10 text-primary border-primary/20">
            {viewBook.year_of_study}
          </Badge>
        )}
        {viewBook?.semester && (
          <Badge variant="outline" className="bg-primary/10 text-primary border-primary/20">
            {viewBook.semester}
          </Badge>
        )}
      </div>
      <div className="flex flex-col gap-6 sm:flex-row">
        {coverUrl && !coverFailed ? (
          <img src={coverUrl} onError={() => setCoverFailed(true)} alt={`${viewBook?.title || 'Book'} cover`} className="h-56 w-40 rounded-lg object-cover shadow-md" />
        ) : (
          <div className="h-56 w-40 shrink-0">
            <DocumentCoverPreview
              type="book"
              title={viewBook?.title || 'Academic Book'}
              code={viewBook?.isbn || viewBook?.category || 'BOOK'}
              yearOfStudy={viewBook?.year_of_study || undefined}
              semester={viewBook?.semester || undefined}
              coverKey={viewBook?.cover_key}
              className="h-56 w-40 rounded-lg shadow-md"
            />
          </div>
        )}
        <div className="min-w-0 flex-1"><h1 className="theme-title mb-4 text-2xl font-bold md:text-3xl">{viewBook?.title || <span className="inline-block h-8 w-3/4 animate-pulse rounded bg-muted" />}</h1>
          <div className="theme-muted grid gap-2 text-sm sm:grid-cols-2">
            {viewBook ? (
              <>
                <p><strong>Authors:</strong> {viewBook.authors.join(', ') || 'Not specified'}</p>
                <p><strong>Publisher:</strong> {viewBook.publisher || 'Not specified'}</p>
                <p><strong>ISBN:</strong> {viewBook.isbn || 'Not specified'}</p>
                <p><Clock className="mr-1 inline h-4 w-4" />{viewBook.publication_year || new Date(viewBook.created_at).getFullYear()}</p>
                {(viewBook.year_of_study || viewBook.semester) && (
                  <p><strong>Level:</strong> {[viewBook.year_of_study, viewBook.semester].filter(Boolean).join(' • ')}</p>
                )}
                <p><strong>Category:</strong> {viewBook.category || viewBook.subject || 'Academic book'}</p>
                <p><Download className="mr-1 inline h-4 w-4" />{viewBook.download_count || 0} downloads</p>
              </>
            ) : (
              [1, 2, 3, 4, 5, 6].map((item) => <span key={item} className="h-4 animate-pulse rounded bg-muted" />)
            )}
          </div>
          {viewBook && <button type="button" onClick={() => navigate(`/profile/${viewBook.uploaded_by}`)} className="theme-soft-panel mt-4 flex items-center gap-3 rounded-xl p-3 text-left"><div className="h-10 w-10 overflow-hidden rounded-full"><AvatarFallback name={displayName} imageUrl={profiles[viewBook.uploaded_by]?.imageUrl || undefined} imageAlt={`${displayName} avatar`} /></div><span><span className="theme-muted block text-xs">Uploaded by</span><span className="theme-title text-sm font-medium">{displayName}</span></span></button>}
        </div>
      </div>
      {viewBook?.description && <p className="theme-soft-panel theme-muted mt-6 rounded-lg p-4">{viewBook.description}</p>}
      <div className="theme-surface-card mt-6 overflow-hidden rounded-xl"><div className="theme-soft-panel flex flex-wrap items-center justify-between gap-3 border-b p-3"><div className="flex items-center gap-2"><Button size="sm" variant="outline" onClick={() => setZoom((value) => Math.max(.6, value - .1))}><ZoomOut className="h-4 w-4" /></Button><span className="theme-muted min-w-16 text-center text-sm">{Math.round(zoom * 100)}%</span><Button size="sm" variant="outline" onClick={() => setZoom((value) => Math.min(2, value + .1))}><ZoomIn className="h-4 w-4" /></Button></div>{fileUrl && <Button size="sm" variant="outline" onClick={() => window.open(fileUrl, '_blank')}><FileText className="mr-2 h-4 w-4" />Open full book</Button>}</div>{fileLoading || fileError ? <DocumentLoadingProgress resourceType="Book" stage={fileLoading ? 'Downloading document…' : 'Document unavailable'} {...(fileProgress || {})} error={fileError} statusHttpCode={fileHttpErrorStatus} onRetry={() => viewBook?.file_key && void loadBookDocument(viewBook.file_key)} onDownload={() => viewBook?.file_key && void handleDownload()} /> : <DocumentPreview src={fileUrl} title={`${viewBook?.title || 'Opening'} book preview`} minHeightClassName="min-h-[700px]" zoom={zoom} onRetry={() => viewBook?.file_key && void loadBookDocument(viewBook.file_key)} />}</div>
      <Button onClick={handleDownload} disabled={!fileUrl || !viewBook} className="theme-accent-bg mt-6"><Download className="mr-2 h-4 w-4" />Download Book</Button>
    </CardContent></Card>
    {viewBook && <TabsSection comments={comments} commentsError={commentsError} retryComments={() => id && void fetchBookComments(Number(id)).then((data) => { setComments(data.items); setCommentsError(false); }).catch(() => setCommentsError(true))} roots={roots} replies={replies} user={user} profiles={profiles} newComment={newComment} replyTarget={replyTarget} replyDraft={replyDraft} submitting={submitting} setNewComment={setNewComment} setReplyTarget={setReplyTarget} setReplyDraft={setReplyDraft} submitComment={submitComment} setComments={setComments} />}
  </div>;
}

function TabsSection({ comments, commentsError, retryComments, roots, replies, user, profiles, newComment, replyTarget, replyDraft, submitting, setNewComment, setReplyTarget, setReplyDraft, submitComment, setComments }: any) {
  return <section><Card className="theme-panel"><CardHeader><CardTitle className="theme-title flex items-center gap-2"><MessageSquare className="h-5 w-5" />Discussion ({comments.length})</CardTitle></CardHeader><CardContent>
    {user ? <div className="mb-5"><Textarea value={newComment} onChange={(event) => setNewComment(event.target.value)} placeholder="Share your thoughts, ask a question, or help others..." rows={3} className="theme-form-input mb-3" /><Button size="sm" onClick={() => void submitComment(newComment)} disabled={!newComment.trim() || submitting} className="theme-accent-bg"><Send className="mr-2 h-4 w-4" />Post Comment</Button></div> : <p className="theme-muted mb-5 text-center">Sign in to join the discussion</p>}
    {commentsError ? <div className="theme-muted py-8 text-center">Comments couldn’t be loaded. <button type="button" className="theme-link-accent underline" onClick={retryComments}>Retry</button></div> : !comments.length ? <div className="theme-muted py-8 text-center"><MessageSquare className="mx-auto mb-3 h-12 w-12 opacity-30" />No comments yet. Be the first to start a discussion!</div> : <div className="space-y-3">{roots.map((comment: Comment) => <Card key={comment.id} className="theme-soft-panel"><CardContent className="p-4"><div className="mb-2 flex items-center gap-2"><div className="h-8 w-8 overflow-hidden rounded-full"><AvatarFallback name={profiles[comment.user_id]?.display_name || `Student ${comment.user_id}`} imageUrl={profiles[comment.user_id]?.imageUrl || undefined} imageAlt="Comment author avatar" /></div><span className="theme-title text-sm font-medium">{profiles[comment.user_id]?.display_name || `Student ${comment.user_id}`}</span><span className="theme-muted text-xs">{comment.created_at ? new Date(comment.created_at).toLocaleDateString() : ''}</span></div><p className="pl-10 text-sm">{comment.content}</p><div className="mt-3 flex gap-2 pl-10"><Button size="sm" variant="ghost" className="theme-muted h-8 px-2" onClick={async () => { try { const updated = await upvoteComment(comment.id); setComments((items: Comment[]) => items.map((item) => item.id === comment.id ? updated : item)); } catch { toast.error('Failed to upvote comment'); } }}><ChevronUp className="mr-1 h-4 w-4" />{comment.upvotes || 0}</Button>{user && <Button size="sm" variant="ghost" className="theme-muted h-8 px-2" onClick={() => setReplyTarget(replyTarget === comment.id ? null : comment.id)}><Reply className="mr-1 h-4 w-4" />Reply</Button>}</div>{replyTarget === comment.id && <div className="mt-3 pl-10"><Textarea value={replyDraft} onChange={(event) => setReplyDraft(event.target.value)} placeholder="Write a reply..." rows={2} className="theme-form-input mb-2" /><Button size="sm" onClick={() => void submitComment(replyDraft, comment.id)} disabled={!replyDraft.trim() || submitting}>Reply</Button></div>}{replies(comment.id).map((reply: Comment) => <div key={reply.id} className="theme-soft-panel mt-3 rounded-lg p-3"><span className="theme-muted text-xs">Reply · {reply.created_at ? new Date(reply.created_at).toLocaleDateString() : ''}</span><p className="mt-1 text-sm">{reply.content}</p></div>)}</CardContent></Card>)}</div>}
  </CardContent></Card></section>;
}
