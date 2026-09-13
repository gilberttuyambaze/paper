import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  fetchPaperById,
  fetchComments,
  fetchSolutions,
  getCachedPaperListSnapshot,
  createComment,
  createSolution,
  createReport,
  upvoteComment,
  upvoteSolution,
  recordPaperDownload,
  trackPaperView,
  runStudyAI,
  saveDocumentOffline,
  getOfflineDocumentUrl,
  getStorageDownloadUrl,
  downloadStorageObject,
  fetchUserProfile,
  fetchAcademicTaxonomy,
  resolvePublicUserProfile,
  resolvePublicUserProfiles,
  reprocessPaper,
  Paper,
  Comment,
  Solution,
} from '../lib/client';
import { useAuth } from '../contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  Download,
  CheckCircle,
  Users,
  BookOpen,
  Clock,
  ArrowLeft,
  MessageSquare,
  Lightbulb,
  Flag,
  User,
  Send,
  FileText,
  GraduationCap,
  ChevronUp,
  Reply,
  ZoomIn,
  ZoomOut,
  Sparkles,
  Maximize2,
  WifiOff,
  Save,
  LoaderCircle,
  Copy,
  Scan,
  FileCheck,
  AlertCircle,
  RefreshCw,
} from 'lucide-react';
import { showMessage, toast } from '@/lib/messages';
import { normalizeApiError } from '@/lib/api-errors';
import AvatarFallback from '../components/AvatarFallback';
import DocumentPreview from '../components/DocumentPreview';
import DocumentLoadingProgress from '../components/DocumentLoadingProgress';
import AIStudyGuideViewer, { StudyChatMessage, AIStudyAction } from '../components/AIStudyGuideViewer';

function VerificationBadge({ status }: { status: string }) {
  if (status === 'verified') {
    return (
      <Badge className="bg-success-soft text-success-foreground hover:bg-success-soft">
        <CheckCircle className="h-3 w-3 mr-1" />
        Verified
      </Badge>
    );
  }
  if (status === 'community') {
    return (
      <Badge className="bg-warning-soft text-warning-foreground hover:bg-warning-soft">
        <Users className="h-3 w-3 mr-1" />
        Community Verified
      </Badge>
    );
  }
  return (
    <Badge className="bg-muted text-muted-foreground hover:bg-muted">
      Unverified
    </Badge>
  );
}

function ExtractionBadge({
  status,
  method,
  quality,
  ocrUsed,
}: {
  status?: string | null;
  method?: string | null;
  quality?: number | null;
  ocrUsed?: boolean | null;
}) {
  if (!status) return null;

  if (status === 'completed') {
    if (ocrUsed || method === 'ocr' || method === 'vision_fallback') {
      return (
        <Badge
          variant="outline"
          className="gap-1 bg-purple-500/10 text-purple-700 dark:text-purple-300 border-purple-500/30 font-medium text-xs"
          title={`Extracted via OCR Engine (${Math.round((quality ?? 1) * 100)}% quality score)`}
        >
          <Scan className="h-3 w-3 text-purple-500" />
          <span>OCR Scanned</span>
        </Badge>
      );
    }
    return (
      <Badge
        variant="outline"
        className="gap-1 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/30 font-medium text-xs"
        title={`Extracted native text (${Math.round((quality ?? 1) * 100)}% quality score)`}
      >
        <FileCheck className="h-3 w-3 text-emerald-500" />
        <span>Verified Text</span>
      </Badge>
    );
  }

  if (status === 'partial') {
    return (
      <Badge
        variant="outline"
        className="gap-1 bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/30 font-medium text-xs"
        title="Document partially read with mixed confidence"
      >
        <AlertCircle className="h-3 w-3 text-amber-500" />
        <span>Partial OCR</span>
      </Badge>
    );
  }

  if (status === 'failed') {
    return (
      <Badge
        variant="outline"
        className="gap-1 bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-500/30 font-medium text-xs"
        title="Document extraction failed"
      >
        <AlertCircle className="h-3 w-3 text-rose-500" />
        <span>Extraction Issue</span>
      </Badge>
    );
  }

  return null;
}

export default function PaperDetails() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user, isAdmin } = useAuth();
  const [paper, setPaper] = useState<Paper | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [commentsError, setCommentsError] = useState(false);
  const [solutions, setSolutions] = useState<Solution[]>([]);
  const [loading, setLoading] = useState(true);
  const [newComment, setNewComment] = useState('');
  const [newSolution, setNewSolution] = useState('');
  const [replyTarget, setReplyTarget] = useState<number | null>(null);
  const [replyDraft, setReplyDraft] = useState('');
  const [reportReason, setReportReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [paperUrl, setPaperUrl] = useState<string | null>(null);
  const [solutionUrl, setSolutionUrl] = useState<string | null>(null);
  const [paperPreviewLoading, setPaperPreviewLoading] = useState(false);
  const [paperProgress, setPaperProgress] = useState<{ loaded: number; total?: number; percent?: number } | null>(null);
  const [paperPreviewError, setPaperPreviewError] = useState<string | null>(null);
  const [pdfZoom, setPdfZoom] = useState(1);
  const [aiResult, setAiResult] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiMode, setAiMode] = useState<AIStudyAction | null>(null);
  const [aiQuestion, setAiQuestion] = useState('');
  const [aiSource, setAiSource] = useState<string | null>(null);
  const [aiFallbackReason, setAiFallbackReason] = useState<string | null>(null);
  const [chatMessages, setChatMessages] = useState<StudyChatMessage[]>([]);
  const [offlinePaperUrl, setOfflinePaperUrl] = useState<string | null>(null);
  const [offlineSolutionUrl, setOfflineSolutionUrl] = useState<string | null>(null);
  const [uploaderImageUrl, setUploaderImageUrl] = useState<string | null>(null);
  const [currentUserImageUrl, setCurrentUserImageUrl] = useState<string | null>(null);
  const [academicNames, setAcademicNames] = useState<Record<string, string>>({});
  const [authorProfiles, setAuthorProfiles] = useState<Record<string, { display_name?: string | null; imageUrl?: string | null }>>({});
  const [isReprocessing, setIsReprocessing] = useState(false);

  const handleReprocessPaper = async () => {
    if (!paper || isReprocessing) return;
    try {
      setIsReprocessing(true);
      const res = await reprocessPaper(paper.id);
      setPaper((prev) =>
        prev
          ? {
              ...prev,
              extraction_status: res.extraction_status,
              extraction_method: res.extraction_method,
              extraction_quality: res.extraction_quality,
              ocr_used: res.ocr_used,
            }
          : prev
      );
      toast.success(res.message || 'Paper reprocessed and indexed successfully!');
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to reprocess document');
    } finally {
      setIsReprocessing(false);
    }
  };

  useEffect(() => {
    if (id) loadPaper(parseInt(id));
  }, [id]);

  useEffect(() => {
    void fetchAcademicTaxonomy().then((taxonomy) => {
      setAcademicNames(Object.fromEntries(taxonomy.nodes.map((node) => [node.id, node.name])));
    }).catch(() => setAcademicNames({}));
  }, []);

  useEffect(() => {
    if (!paper?.id || !user) return;
    void trackPaperView(paper.id);
  }, [paper?.id, user]);

  useEffect(() => {
    let cancelled = false;
    async function loadCurrentUserImage() {
      if (!user) {
        setCurrentUserImageUrl(null);
        return;
      }
      try {
        const profile = await fetchUserProfile();
        if (cancelled) return;
        if (!profile || !profile.profile_picture_key) {
          setCurrentUserImageUrl(null);
          return;
        }
        if (/^https?:\/\//i.test(profile.profile_picture_key)) {
          setCurrentUserImageUrl(profile.profile_picture_key);
          return;
        }
        const url = await getStorageDownloadUrl('profiles', profile.profile_picture_key);
        if (!cancelled) setCurrentUserImageUrl(url);
      } catch (e) {
        if (!cancelled) setCurrentUserImageUrl(null);
      }
    }

    void loadCurrentUserImage();
    return () => {
      cancelled = true;
    };
  }, [user]);

  useEffect(() => {
    let cancelled = false;

    if (!paper?.uploader_profile_picture_key) {
      setUploaderImageUrl(null);
    } else {
      void getStorageDownloadUrl('profiles', paper.uploader_profile_picture_key)
        .then((url) => {
          if (!cancelled) setUploaderImageUrl(url);
        })
        .catch(() => {
          if (!cancelled) setUploaderImageUrl(null);
        });
    }

    return () => {
      cancelled = true;
    };
  }, [paper?.uploader_profile_picture_key]);

  useEffect(() => {
    let cancelled = false;
    const ids = new Set<string>();
    comments.forEach((c) => ids.add(c.user_id));
    solutions.forEach((s) => ids.add(s.user_id));
    // Also include uploader
    if (paper?.user_id) ids.add(paper.user_id);

    const toFetch = Array.from(ids).filter((id) => !authorProfiles[id] && id !== user?.id);
    if (toFetch.length === 0) return;

    (async () => {
      const resolved = await resolvePublicUserProfiles(toFetch);
      if (cancelled) return;
      const next: Record<string, { display_name?: string | null; imageUrl?: string | null }> = {};
      for (const [uid, data] of Object.entries(resolved)) {
        next[uid] = { display_name: data.profile?.display_name || null, imageUrl: data.imageUrl || null };
      }
      setAuthorProfiles((prev) => ({ ...prev, ...next }));
    })();

    return () => {
      cancelled = true;
    };
  }, [comments, solutions, paper?.user_id]);

  const loadPaper = async (paperId: number) => {
    try {
      setLoading(true);
      setPaperUrl(null);
      setSolutionUrl(null);
      setPaperPreviewLoading(false);
      const cached = getCachedPaperListSnapshot();
      const cachedPaper = cached?.items.find((item) => item.id === paperId) || null;
      if (cachedPaper) {
        setPaper(cachedPaper);
        setLoading(false);
      }
      const [paperResult, commentsResult, solutionsResult] = await Promise.allSettled([
        fetchPaperById(paperId),
        fetchComments(paperId),
        fetchSolutions(paperId),
      ]);

      if (paperResult.status !== 'fulfilled') {
        throw paperResult.reason;
      }

      const paperData = paperResult.value;
      const commentsData = commentsResult.status === 'fulfilled' ? commentsResult.value : { items: [] };
      setCommentsError(commentsResult.status !== 'fulfilled');
      const solutionsData = solutionsResult.status === 'fulfilled' ? solutionsResult.value : { items: [] };

      setPaper(paperData);
      setComments(commentsData.items);
      setSolutions(solutionsData.items);
      void hydratePaperAssets(paperData);
    } catch (err) {
      console.error('Failed to load paper:', err);
      toast.error('Failed to load paper details');
    } finally {
      setLoading(false);
    }
  };

  const [paperHttpErrorStatus, setPaperHttpErrorStatus] = useState<number | null>(null);

  const retryComments = async () => {
    if (!id) return;
    try {
      const commentsData = await fetchComments(Number(id));
      setComments(commentsData.items || []);
      setCommentsError(false);
    } catch {
      setCommentsError(true);
    }
  };

  const loadDownloadUrl = async (
    objectKey: string,
    setter: React.Dispatch<React.SetStateAction<string | null>>,
    isMainPaper = false
  ) => {
    try {
      if (isMainPaper) setPaperHttpErrorStatus(null);
      const downloadUrl = await downloadStorageObject('papers', objectKey, (progress) => {
        if (isMainPaper) setPaperProgress(progress);
      });
      setter(downloadUrl);
    } catch (err: any) {
      setter(null);
      const status = err?.response?.status || null;
      if (isMainPaper) {
        setPaperHttpErrorStatus(status);
        if (status === 404) {
          setPaperPreviewError('This file could not be found in storage.');
        } else if (status === 403) {
          setPaperPreviewError("You don't have permission to access this document.");
        } else {
          setPaperPreviewError('The document could not be retrieved from storage.');
        }
      }
    }
  };

  const hydratePaperAssets = async (paperData: Paper) => {
    setPaperPreviewLoading(Boolean(paperData.file_key));
    setPaperPreviewError(null);
    setPaperHttpErrorStatus(null);
    setPaperProgress(paperData.file_key ? { loaded: 0 } : null);
    const tasks: Promise<void>[] = [];

    tasks.push(
      getOfflineDocumentUrl('paper', paperData.id).then((localUrl) => setOfflinePaperUrl(localUrl))
    );
    tasks.push(
      getOfflineDocumentUrl('solution', paperData.id).then((localUrl) => setOfflineSolutionUrl(localUrl))
    );

    if (paperData.file_key) {
      tasks.push(loadDownloadUrl(paperData.file_key, setPaperUrl, true));
    }
    if (paperData.solution_key) {
      tasks.push(loadDownloadUrl(paperData.solution_key, setSolutionUrl, false));
    }

    await Promise.allSettled(tasks);
    setPaperPreviewLoading(false);
  };

  const handleDownload = async () => {
    if (!paper?.file_key) return;
    try {
      const downloadUrl = await getStorageDownloadUrl('papers', paper.file_key);
      if (downloadUrl) {
        window.open(downloadUrl, '_blank');
        const updated = await recordPaperDownload(paper.id);
        setPaper((prev) => (prev ? { ...prev, download_count: updated.download_count } : prev));
      }
      toast.success('Download started');
    } catch {
      toast.error('Download failed. The file may not be available yet.');
    }
  };

  const handleSubmitComment = async () => {
    if (!newComment.trim() || !paper || !user) return;
    try {
      setSubmitting(true);
      const comment = await createComment({ paper_id: paper.id, content: newComment.trim() });
      setComments((prev) => [comment, ...prev]);
      setNewComment('');
      toast.success('Comment posted');
    } catch {
      toast.error('Failed to post comment');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmitSolution = async () => {
    if (!newSolution.trim() || !paper || !user) return;
    try {
      setSubmitting(true);
      const solution = await createSolution({ paper_id: paper.id, content: newSolution.trim() });
      setSolutions((prev) =>
        [solution, ...prev].sort((a, b) => (b.upvotes || 0) - (a.upvotes || 0))
      );
      setNewSolution('');
      toast.success('Solution submitted');
    } catch {
      toast.error('Failed to submit solution');
    } finally {
      setSubmitting(false);
    }
  };

  const handleReport = async () => {
    if (!reportReason.trim() || !paper || !user) return;
    try {
      setSubmitting(true);
      const response = await createReport({ paper_id: paper.id, reason: reportReason.trim() });
      setPaper((prev) =>
        prev
          ? {
              ...prev,
              report_count: response.paper.report_count,
              is_hidden: response.paper.is_hidden,
            }
          : prev
      );
      setReportReason('');
      setReportOpen(false);
      toast.success('Report submitted. Thank you for helping maintain quality.');
    } catch {
      toast.error('Failed to submit report');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="animate-pulse space-y-6">
          <div className="h-8 w-3/4 rounded bg-muted" />
          <div className="h-4 w-1/2 rounded bg-muted" />
          <div className="h-48 rounded bg-muted" />
        </div>
      </div>
    );
  }

  const handleReplySubmit = async (parentId: number) => {
    if (!replyDraft.trim() || !paper || !user) return;
    try {
      setSubmitting(true);
      const comment = await createComment({
        paper_id: paper.id,
        content: replyDraft.trim(),
        parent_id: parentId,
      });
      setComments((prev) => [comment, ...prev]);
      setReplyDraft('');
      setReplyTarget(null);
      toast.success('Reply posted');
    } catch {
      toast.error('Failed to post reply');
    } finally {
      setSubmitting(false);
    }
  };

  const handleCommentVote = async (commentId: number) => {
    try {
      const updated = await upvoteComment(commentId);
      setComments((prev) => prev.map((comment) => (comment.id === commentId ? updated : comment)));
    } catch {
      toast.error('Failed to upvote comment');
    }
  };

  const handleSolutionVote = async (solutionId: number) => {
    try {
      const updated = await upvoteSolution(solutionId);
      setSolutions((prev) =>
        prev
          .map((solution) => (solution.id === solutionId ? updated : solution))
          .sort((a, b) => (b.upvotes || 0) - (a.upvotes || 0))
      );
    } catch {
      toast.error('Failed to upvote solution');
    }
  };

  const rootComments = comments
    .filter((comment) => !comment.parent_id)
    .sort((a, b) => {
      const votes = (b.upvotes || 0) - (a.upvotes || 0);
      if (votes !== 0) return votes;
      return (new Date(b.created_at || 0).getTime() || 0) - (new Date(a.created_at || 0).getTime() || 0);
    });

  const getReplies = (parentId: number) =>
    comments
      .filter((comment) => comment.parent_id === parentId)
      .sort((a, b) => (new Date(a.created_at || 0).getTime() || 0) - (new Date(b.created_at || 0).getTime() || 0));

  const promptSignInForAI = () => {
    const returnUrl = encodeURIComponent(window.location.pathname + window.location.search);
    showMessage({
      type: 'info',
      title: 'Sign in to use AI Study Assistant',
      message: 'To use the AI Study Assistant, practice quizzes, step-by-step revision, and formula guides, please sign in to your account or create a free account.',
      actions: [
        {
          label: 'Sign In',
          variant: 'default',
          onClick: () => {
            navigate(`/login?returnTo=${returnUrl}`);
          },
        },
        {
          label: 'Create Account',
          variant: 'outline',
          onClick: () => {
            navigate(`/register?returnTo=${returnUrl}`);
          },
        },
        {
          label: 'Cancel',
          variant: 'outline',
          onClick: () => undefined,
        },
      ],
    });
  };

  const handleAIAction = async (action: AIStudyAction, questionOverride?: string, preferredProvider?: string) => {
    if (!paper) return;
    if (!user) {
      promptSignInForAI();
      return;
    }

    const targetQuestion = (questionOverride !== undefined ? questionOverride : aiQuestion).trim();
    if (action === 'question' && !targetQuestion) {
      toast.error('Write a question about this paper first.');
      return;
    }

    let promptDisplay = targetQuestion;
    if (action === 'explain') promptDisplay = 'Generate a comprehensive study breakdown and revision strategy for this exam paper.';
    else if (action === 'summarize') promptDisplay = 'Summarize key themes, verified solutions, and community discussions for this paper.';
    else if (action === 'formulas') promptDisplay = 'What are the essential formulas, equations, definitions, and theorems required for this exam?';
    else if (action === 'pitfalls') promptDisplay = 'What are the most common student pitfalls, traps, and grading mistakes to avoid?';
    else if (action === 'quiz') promptDisplay = 'Generate a 3-question practice quiz with step-by-step solutions for this paper.';

    const userMessage: StudyChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: promptDisplay,
      action,
      timestamp: new Date(),
    };

    setChatMessages((prev) => [...prev, userMessage]);
    setAiLoading(true);
    setAiMode(action);

    const historyPayload = chatMessages.slice(-6).map((m) => ({
      role: m.role,
      content: m.content,
    }));

    try {
      const response = await runStudyAI(
        paper.id,
        action,
        action === 'question' ? targetQuestion : undefined,
        historyPayload,
        preferredProvider
      );

      const assistantMessage: StudyChatMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: response.content,
        action,
        model: response.model,
        provider: response.provider,
        fallbackReason: response.fallback_reason || null,
        duration_ms: response.duration_ms,
        sources: response.sources,
        usage: response.usage,
        timestamp: new Date(),
      };

      setChatMessages((prev) => [...prev, assistantMessage]);
      setAiResult(response.content);
      setAiSource(response.model);
      setAiFallbackReason(response.fallback_reason || null);
    } catch (error: any) {
      if (error?.response?.status === 401) {
        setChatMessages((prev) => prev.filter((m) => m.id !== userMessage.id));
        promptSignInForAI();
        return;
      }
      toast.error(normalizeApiError(error).message || 'AI assistant is unavailable right now');
    } finally {
      setAiLoading(false);
    }
  };

  const handleClearChat = () => {
    setChatMessages([]);
    setAiResult('');
    setAiSource(null);
    setAiFallbackReason(null);
    setAiMode(null);
    toast.info('Study conversation reset');
  };

  const handleSaveOffline = async (kind: 'paper' | 'solution') => {
    if (!paper) return;
    const sourceUrl = kind === 'paper' ? paperUrl : solutionUrl;
    if (!sourceUrl) {
      toast.error('No preview URL is available to save offline');
      return;
    }
    try {
      const cachedUrl = await saveDocumentOffline(sourceUrl, kind, paper.id);
      if (kind === 'paper') {
        setOfflinePaperUrl(cachedUrl);
      } else {
        setOfflineSolutionUrl(cachedUrl);
      }
      toast.success(`${kind === 'paper' ? 'Paper' : 'Solution'} saved for offline use`);
    } catch (error: any) {
      toast.error(error?.message || 'Failed to save document offline');
    }
  };

  if (!paper) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center">
        <h2 className="theme-title mb-4 text-2xl font-bold">Paper Not Found</h2>
        <Button onClick={() => navigate('/search')} className="theme-accent-bg">
          Browse Resources
        </Button>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Back Button */}
      <Button
        variant="ghost"
        onClick={() => navigate(-1)}
        className="theme-muted mb-6 hover:bg-secondary hover:text-secondary-foreground"
      >
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back
      </Button>

      {/* Paper Header */}
      <Card className="theme-panel mb-6">
        <CardContent className="p-6">
          <div className="flex flex-wrap items-center gap-2 mb-4">
            <Badge variant="outline" className="border-primary text-primary">
              {paper.paper_type}
            </Badge>
            <VerificationBadge status={paper.verification_status} />
            <Badge variant="outline">
              {paper.year}
            </Badge>
            {paper.year_of_study && (
              <Badge variant="outline" className="bg-primary/10 text-primary border-primary/20">
                {paper.year_of_study}
              </Badge>
            )}
            {paper.semester && (
              <Badge variant="outline" className="bg-primary/10 text-primary border-primary/20">
                {paper.semester}
              </Badge>
            )}
            {paper.report_count && paper.report_count > 0 && (
              <Badge className="theme-error-note border-0 hover:bg-inherit">
                <Flag className="h-3 w-3 mr-1" />
                Reported {paper.report_count}
              </Badge>
            )}
            {paper.is_hidden && (
              <Badge className="theme-error-note border-0 hover:bg-inherit">
                Hidden from public
              </Badge>
            )}
            <ExtractionBadge
              status={paper.extraction_status}
              method={paper.extraction_method}
              quality={paper.extraction_quality}
              ocrUsed={paper.ocr_used}
            />
            {(isAdmin || (user && user.id === paper.user_id) || paper.extraction_status === 'failed' || paper.extraction_status === 'partial') && Boolean(paper.file_key) && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleReprocessPaper}
                disabled={isReprocessing}
                className="h-6 px-2 text-[11px] gap-1 border-border/80 hover:border-primary text-muted-foreground hover:text-foreground"
                title="Reprocess document extraction and re-index questions"
              >
                <RefreshCw className={`h-3 w-3 ${isReprocessing ? 'animate-spin text-primary' : ''}`} />
                <span>{isReprocessing ? 'Processing...' : 'Reprocess AI Index'}</span>
              </Button>
            )}
          </div>

          <h1 className="theme-title mb-4 text-2xl font-bold md:text-3xl">
            {paper.title}
          </h1>

          <div className="theme-muted grid grid-cols-1 gap-4 text-sm md:grid-cols-2">
            <div className="space-y-2">
              <p className="flex items-center gap-2">
                <BookOpen className="theme-section-icon h-4 w-4" />
                <span className="font-medium">{paper.course_code}</span> - {paper.course_name}
              </p>
              {(paper.year_of_study || paper.semester) && (
                <p className="flex items-center gap-2">
                  <GraduationCap className="theme-section-icon h-4 w-4" />
                  <span>Academic Level: {[paper.year_of_study, paper.semester].filter(Boolean).join(' • ')}</span>
                </p>
              )}
              <p className="flex items-center gap-2">
                <GraduationCap className="theme-section-icon h-4 w-4" />
                {paper.college}
              </p>
              <p className="flex items-center gap-2">
                <FileText className="theme-section-icon h-4 w-4" />
                {paper.department}
              </p>
              {paper.campus_id && academicNames[paper.campus_id] && (
                <div className="theme-soft-panel rounded-xl p-3 text-sm">
                  <p>{academicNames[paper.campus_id]}</p>
                  {paper.college_id && academicNames[paper.college_id] && <p>{academicNames[paper.college_id]}</p>}
                  {paper.school_id && academicNames[paper.school_id] && <p>{academicNames[paper.school_id]}</p>}
                  {paper.programme_id && paper.programme_id !== 'other' && academicNames[paper.programme_id] && <p>{academicNames[paper.programme_id]}</p>}
                  {paper.programme_id === 'other' && <p>Programme not listed</p>}
                </div>
              )}
            </div>
            <div className="space-y-2">
              {paper.lecturer && (
                <p className="flex items-center gap-2">
                  <User className="theme-section-icon h-4 w-4" />
                  {paper.lecturer}
                </p>
              )}
              <button
                type="button"
                onClick={() => navigate(`/profile/${paper.user_id}`)}
                className="theme-soft-panel flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-left transition-colors hover:bg-secondary"
              >
                  <div className="theme-accent-soft h-11 w-11 overflow-hidden rounded-full text-sm">
                    <AvatarFallback
                      name={authorProfiles[paper.user_id]?.display_name || paper.uploader_display_name || (paper.user_id ? `Contributor ${paper.user_id}` : 'Academic Contributor')}
                      imageUrl={authorProfiles[paper.user_id]?.imageUrl ?? uploaderImageUrl ?? undefined}
                      imageAlt={`${authorProfiles[paper.user_id]?.display_name || paper.uploader_display_name || 'Contributor'} profile picture`}
                    />
                  </div>
                  <div className="min-w-0">
                    <p className="theme-muted text-xs uppercase tracking-[0.2em]">Uploaded by</p>
                    <p className="theme-title truncate text-sm font-medium">
                      {authorProfiles[paper.user_id]?.display_name || paper.uploader_display_name || (paper.user_id ? `Contributor ${paper.user_id}` : 'Academic Contributor')}
                    </p>
                    <p className="theme-link-accent text-xs">View uploader profile</p>
                  </div>
              </button>
              <p className="flex items-center gap-2">
                <Clock className="theme-section-icon h-4 w-4" />
                {paper.created_at ? new Date(paper.created_at).toLocaleDateString() : 'N/A'}
              </p>
              <p className="flex items-center gap-2">
                <Download className="theme-section-icon h-4 w-4" />
                {paper.download_count || 0} downloads
              </p>
            </div>
          </div>

          {paper.description && (
            <p className="theme-soft-panel theme-muted mt-4 rounded-lg p-4">
              {paper.description}
            </p>
          )}

          {(paperUrl || offlinePaperUrl) ? (
            <div className="theme-surface-card mt-6 overflow-hidden rounded-xl">
              <div className="theme-soft-panel flex flex-wrap items-center justify-between gap-3 border-b p-3">
                <div className="flex items-center gap-2">
                  <Button type="button" size="sm" variant="outline" onClick={() => setPdfZoom((prev) => Math.max(0.6, prev - 0.1))}>
                    <ZoomOut className="h-4 w-4" />
                  </Button>
                  <span className="theme-muted min-w-16 text-center text-sm">{Math.round(pdfZoom * 100)}%</span>
                  <Button type="button" size="sm" variant="outline" onClick={() => setPdfZoom((prev) => Math.min(2, prev + 0.1))}>
                    <ZoomIn className="h-4 w-4" />
                  </Button>
                  <Button type="button" size="sm" variant="outline" onClick={() => setPdfZoom(1)}>Reset</Button>
                </div>
                <div className="flex items-center gap-2">
                  <Button type="button" size="sm" variant="outline" onClick={() => handleSaveOffline('paper')}>
                    <Save className="mr-2 h-4 w-4" />
                    Save Offline
                  </Button>
                  {offlinePaperUrl && (
                    <Badge variant="secondary" className="gap-1">
                      <WifiOff className="h-3 w-3" />
                      Offline Ready
                    </Badge>
                  )}
                  <Button type="button" size="sm" variant="outline" onClick={() => window.open(paperUrl || offlinePaperUrl!, '_blank')}>
                    <Maximize2 className="mr-2 h-4 w-4" />
                    Open Fullscreen
                  </Button>
                </div>
              </div>
              <DocumentPreview src={paperUrl || offlinePaperUrl} title={`${paper.title} paper preview`} minHeightClassName="min-h-[700px]" zoom={pdfZoom} />
            </div>
          ) : (paperPreviewLoading || paper.file_key) ? (
            <div className="mt-6">
              <DocumentLoadingProgress
                resourceType="Paper"
                stage="Downloading document…"
                {...(paperProgress || {})}
                error={paperPreviewError}
                statusHttpCode={paperHttpErrorStatus}
                onRetry={() => void hydratePaperAssets(paper)}
                onDownload={() => void handleDownload()}
              />
            </div>
          ) : (
            <div className="mt-6"><DocumentPreview title={`${paper.title} paper preview`} unavailableMessage="Paper preview is not available. Use the download button to view the full document." /></div>
          )}

          <div className="mt-6">
            <AIStudyGuideViewer
              content={aiResult}
              model={aiSource}
              mode={aiMode}
              loading={aiLoading}
              fallbackReason={aiFallbackReason}
              messages={chatMessages}
              isAuthenticated={Boolean(user)}
              onRequireAuth={promptSignInForAI}
              onSendMessage={(action, question, provider) => void handleAIAction(action, question, provider)}
              onClearMessages={handleClearChat}
              onQuickAction={(promptText) => void handleAIAction('question', promptText)}
            />
          </div>

          {/* Action Buttons */}
          <div className="flex flex-wrap gap-3 mt-6">
            <Button
              onClick={handleDownload}
              className="theme-accent-bg"
              disabled={!paper.file_key}
            >
              <Download className="h-4 w-4 mr-2" />
              Download Paper
            </Button>
            {paper.solution_key && (
              <>
                <Button
                  variant="outline"
                  onClick={async () => {
                    try {
                      const downloadUrl = await getStorageDownloadUrl('papers', paper.solution_key!);
                      if (downloadUrl) {
                        window.open(downloadUrl, '_blank');
                      }
                    } catch {
                      toast.error('Solution download failed');
                    }
                  }}
                >
                  <Lightbulb className="h-4 w-4 mr-2" />
                  Download Solution
                </Button>
                <Button variant="outline" onClick={() => handleSaveOffline('solution')}>
                  <Save className="mr-2 h-4 w-4" />
                  Save Solution Offline
                </Button>
              </>
            )}
            {user && (
              <Dialog open={reportOpen} onOpenChange={setReportOpen}>
                <DialogTrigger asChild>
                  <Button
                    variant="outline"
                    className="border-error-border text-error hover:bg-error-soft hover:text-error-foreground"
                  >
                    <Flag className="h-4 w-4 mr-2" />
                    Report
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Report Paper</DialogTitle>
                    <DialogDescription>
                      Tell us why this paper should be reviewed. Your report helps moderators check
                      quality, accuracy, and policy issues.
                    </DialogDescription>
                  </DialogHeader>
                  <Textarea
                    value={reportReason}
                    onChange={(e) => setReportReason(e.target.value)}
                    placeholder="Describe the issue (e.g., wrong content, duplicate, inappropriate)..."
                    rows={4}
                  />
                  <Button
                    onClick={handleReport}
                    disabled={!reportReason.trim() || submitting}
                    className="bg-error text-error-foreground hover:bg-error/90"
                  >
                    Submit Report
                  </Button>
                </DialogContent>
              </Dialog>
            )}
          </div>

          {(solutionUrl || offlineSolutionUrl) && (
            <Card className="theme-panel mt-6">
              <CardHeader>
                <CardTitle className="theme-title flex items-center gap-2">
                  Solution Preview
                  {offlineSolutionUrl && (
                    <Badge variant="secondary" className="gap-1">
                      <WifiOff className="h-3 w-3" />
                      Offline Ready
                    </Badge>
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0"><DocumentPreview src={solutionUrl || offlineSolutionUrl} title={`${paper.title} solution preview`} /></CardContent>
            </Card>
          )}
        </CardContent>
      </Card>

      {/* Discussion & Solutions Tabs */}
      <Tabs defaultValue="discussion" className="space-y-4">
        <TabsList className="theme-soft-panel">
          <TabsTrigger value="discussion" className="flex items-center gap-2">
            <MessageSquare className="h-4 w-4" />
            Discussion ({comments.length})
          </TabsTrigger>
          <TabsTrigger value="solutions" className="flex items-center gap-2">
            <Lightbulb className="h-4 w-4" />
            Solutions ({solutions.length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="discussion">
          {/* New Comment */}
          {user ? (
            <Card className="theme-panel mb-4">
              <CardContent className="p-4">
                <Textarea
                  value={newComment}
                  onChange={(e) => setNewComment(e.target.value)}
                  placeholder="Share your thoughts, ask a question, or help others..."
                  rows={3}
                  className="theme-form-input mb-3"
                />
                <Button
                  onClick={handleSubmitComment}
                  disabled={!newComment.trim() || submitting}
                  className="theme-accent-bg"
                  size="sm"
                >
                  <Send className="h-4 w-4 mr-2" />
                  Post Comment
                </Button>
              </CardContent>
            </Card>
          ) : (
            <Card className="theme-panel mb-4">
              <CardContent className="theme-muted p-4 text-center">
                <p>Sign in to join the discussion</p>
              </CardContent>
            </Card>
          )}

          {/* Comments List */}
          {commentsError ? <div className="theme-muted py-8 text-center">Comments couldn’t be loaded. <button type="button" className="theme-link-accent underline" onClick={() => void retryComments()}>Retry</button></div> : comments.length === 0 ? (
            <Card className="theme-panel">
              <CardContent className="theme-muted p-8 text-center">
                <MessageSquare className="h-12 w-12 mx-auto mb-3 opacity-30" />
                <p>No comments yet. Be the first to start a discussion!</p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {rootComments.map((comment) => (
                <Card key={comment.id} className="theme-panel">
                  <CardContent className="p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <div className="theme-accent-soft h-8 w-8 overflow-hidden rounded-full text-xs">
                        {
                          (() => {
                            const p = authorProfiles[comment.user_id];
                            const name = p?.display_name || `Student ${comment.user_id}`;
                            const img = p?.imageUrl ?? (comment.user_id === user?.id ? currentUserImageUrl : null);
                            return <AvatarFallback name={name} imageUrl={img ?? undefined} imageAlt={`${name} avatar`} />;
                          })()
                        }
                      </div>
                      <span className="theme-title text-sm font-medium">{authorProfiles[comment.user_id]?.display_name || `Student ${comment.user_id}`}</span>
                      <span className="theme-muted text-xs">
                        {comment.created_at ? new Date(comment.created_at).toLocaleDateString() : ''}
                      </span>
                    </div>
                    <p className="pl-10 text-sm text-foreground">{comment.content}</p>
                    <div className="mt-3 flex items-center gap-2 pl-10">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleCommentVote(comment.id)}
                        className="theme-muted h-8 px-2 hover:text-primary"
                      >
                        <ChevronUp className="mr-1 h-4 w-4" />
                        {comment.upvotes || 0}
                      </Button>
                      {user && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setReplyTarget(replyTarget === comment.id ? null : comment.id)}
                          className="theme-muted h-8 px-2 hover:text-primary"
                        >
                          <Reply className="mr-1 h-4 w-4" />
                          Reply
                        </Button>
                      )}
                    </div>
                    {replyTarget === comment.id && (
                      <div className="mt-3 pl-10">
                        <Textarea
                          value={replyDraft}
                          onChange={(e) => setReplyDraft(e.target.value)}
                          placeholder="Write a reply..."
                          rows={2}
                          className="theme-form-input mb-2"
                        />
                        <Button
                          size="sm"
                          onClick={() => handleReplySubmit(comment.id)}
                          disabled={!replyDraft.trim() || submitting}
                          className="theme-accent-bg"
                        >
                          Reply
                        </Button>
                      </div>
                    )}
                    {getReplies(comment.id).length > 0 && (
                      <div className="mt-4 space-y-2 pl-10">
                        {getReplies(comment.id).map((reply) => (
                          <div
                            key={reply.id}
                            className="theme-soft-panel rounded-lg p-3"
                          >
                            <div className="mb-1 flex items-center gap-2">
                              <span className="theme-title text-xs font-medium">Reply</span>
                              <span className="theme-muted text-xs">
                                {reply.created_at ? new Date(reply.created_at).toLocaleDateString() : ''}
                              </span>
                            </div>
                            <p className="text-sm text-foreground">{reply.content}</p>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => handleCommentVote(reply.id)}
                              className="theme-muted mt-2 h-8 px-2 hover:text-primary"
                            >
                              <ChevronUp className="mr-1 h-4 w-4" />
                              {reply.upvotes || 0}
                            </Button>
                          </div>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="solutions">
          {/* New Solution */}
          {user ? (
            <Card className="theme-panel mb-4">
              <CardHeader>
                <CardTitle className="theme-title text-lg">Submit a Solution</CardTitle>
              </CardHeader>
              <CardContent>
                <Textarea
                  value={newSolution}
                  onChange={(e) => setNewSolution(e.target.value)}
                  placeholder="Write your solution or explanation here..."
                  rows={5}
                  className="theme-form-input mb-3"
                />
                <Button
                  onClick={handleSubmitSolution}
                  disabled={!newSolution.trim() || submitting}
                  className="theme-accent-bg"
                  size="sm"
                >
                  <Lightbulb className="h-4 w-4 mr-2" />
                  Submit Solution
                </Button>
              </CardContent>
            </Card>
          ) : (
            <Card className="theme-panel mb-4">
              <CardContent className="theme-muted p-4 text-center">
                <p>Sign in to submit a solution</p>
              </CardContent>
            </Card>
          )}

          {/* Solutions List */}
          {solutions.length === 0 ? (
            <Card className="theme-panel">
              <CardContent className="theme-muted p-8 text-center">
                <Lightbulb className="h-12 w-12 mx-auto mb-3 opacity-30" />
                <p>No solutions yet. Be the first to help!</p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {solutions.map((solution) => (
                <Card key={solution.id} className="theme-panel">
                  <CardContent className="p-4">
                    <div className="flex items-center gap-2 mb-3">
                      <div className="theme-accent-soft h-8 w-8 overflow-hidden rounded-full text-xs">
                        {
                          (() => {
                            const p = authorProfiles[solution.user_id];
                            const name = p?.display_name || `Contributor ${solution.user_id}`;
                            const img = p?.imageUrl ?? (solution.user_id === user?.id ? currentUserImageUrl : null);
                            return <AvatarFallback name={name} imageUrl={img ?? undefined} imageAlt={`${name} avatar`} />;
                          })()
                        }
                      </div>
                      <span className="theme-title text-sm font-medium">{authorProfiles[solution.user_id]?.display_name || `Contributor ${solution.user_id}`}</span>
                      {solution.is_best && <Badge className="theme-status-badge--verified hover:bg-inherit">Best Answer</Badge>}
                      <span className="theme-muted ml-auto text-xs">
                        {solution.created_at ? new Date(solution.created_at).toLocaleDateString() : ''}
                      </span>
                    </div>
                    <p className="pl-10 whitespace-pre-wrap text-sm text-foreground">
                      {solution.content}
                    </p>
                    <div className="mt-3 pl-10">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleSolutionVote(solution.id)}
                        className="theme-muted h-8 px-2 hover:text-primary"
                      >
                        <ChevronUp className="mr-1 h-4 w-4" />
                        {solution.upvotes || 0}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
