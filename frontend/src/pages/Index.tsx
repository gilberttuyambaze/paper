import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  fetchAllPapers,
  fetchPersonalizedRecommendations,
  getCachedPaperListSnapshot,
  getCachedPersonalizedRecommendationsSnapshot,
  Paper,
  PersonalizedRecommendationsResponse,
  resolvePublicUserProfiles,
} from '../lib/client';
import { fetchBooks, type Book } from '../lib/books';
import AvatarFallback from '../components/AvatarFallback';
import OfflineDataBanner from '../components/OfflineDataBanner';
import ExpandableContentSection from '../components/ExpandableContentSection';
import DocumentCoverPreview from '../components/DocumentCoverPreview';
import { useAuth } from '../contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import {
  Search,
  Download,
  FileText,
  Users,
  CheckCircle,
  TrendingUp,
  ArrowRight,
  BookOpen,
  Clock,
  Star,
  Upload,
  Sparkles,
} from 'lucide-react';

const HERO_IMAGE = '/assets/illustrations/landing.jpg';
const COLLAB_IMAGE = '/assets/illustrations/peer-collaboration.svg';

const PAPER_TYPES = ['Exam', 'CAT', 'Assignment', 'GroupWork'];

function VerificationBadge({ status }: { status: string }) {
  if (status === 'verified') {
    return (
      <Badge className="theme-status-badge--verified hover:bg-inherit">
        <CheckCircle className="h-3 w-3 mr-1" />
        Verified
      </Badge>
    );
  }
  if (status === 'community') {
    return (
      <Badge className="theme-status-badge--community hover:bg-inherit">
        <Users className="h-3 w-3 mr-1" />
        Community
      </Badge>
    );
  }
  return (
      <Badge className="bg-muted text-muted-foreground hover:bg-muted">
      Unverified
    </Badge>
  );
}

function PaperCard({ paper, uploaderProfiles }: { paper: Paper; uploaderProfiles?: Record<string, { profile?: any; imageUrl?: string | null }>; }) {
  const uploaderName = uploaderProfiles?.[paper.user_id]?.profile?.display_name || paper.uploader_display_name || (paper.user_id ? `Contributor ${paper.user_id}` : 'Academic Contributor');
  const uploaderAvatar = uploaderProfiles?.[paper.user_id]?.imageUrl ?? (paper.uploader_profile_picture_key || undefined);

  return (
    <Link to={`/paper/${paper.id}`} className="block group">
      <Card className="theme-panel h-full overflow-hidden border transition-all duration-300 hover:-translate-y-1 hover:shadow-lg flex flex-col justify-between">
        <div className="p-2.5 pb-0 sm:p-3 sm:pb-0">
          <DocumentCoverPreview
            title={paper.title}
            courseCode={paper.course_code}
            courseName={paper.course_name}
            year={paper.year}
            yearOfStudy={paper.year_of_study}
            semester={paper.semester}
            paperType={paper.paper_type}
            department={paper.department}
            verificationStatus={paper.verification_status}
            hasSolution={Boolean(paper.solution_key)}
            isBook={false}
            size="md"
            className="group-hover:scale-[1.01] transition-transform"
          />
        </div>
        <CardContent className="p-2.5 pt-2 sm:p-3 sm:pt-2 flex flex-col justify-between flex-1 gap-1.5">
          <div>
            <div className="flex flex-wrap items-center justify-between gap-1 mb-1">
              <div className="flex flex-wrap items-center gap-1">
                <Badge variant="outline" className="border-primary text-[10px] sm:text-xs font-semibold text-primary px-1.5 py-0">
                  {paper.paper_type}
                </Badge>
                {(paper.year_of_study || paper.semester) && (
                  <Badge variant="secondary" className="text-[10px] sm:text-xs font-medium px-1.5 py-0">
                    {[paper.year_of_study, paper.semester].filter(Boolean).join(' · ')}
                  </Badge>
                )}
              </div>
              <VerificationBadge status={paper.verification_status} />
            </div>
            <h3 className="theme-title mb-1 line-clamp-1 font-bold transition-colors group-hover:text-primary text-sm sm:text-base" title={paper.title}>
              {paper.title}
            </h3>
            <div className="theme-muted space-y-0.5 text-xs">
              <p className="flex items-center gap-1 font-medium text-foreground/85 truncate">
                <BookOpen className="h-3 w-3 shrink-0 text-primary" />
                <span className="truncate">{paper.course_code} - {paper.course_name}</span>
              </p>
              <p className="flex items-center gap-1 truncate text-muted-foreground">
                <Clock className="h-3 w-3 shrink-0" />
                <span className="truncate">{paper.year} · {paper.department}</span>
              </p>
            </div>
          </div>
          <div>
            <div className="mt-1 pt-2 border-t border-border/40 flex items-center justify-between gap-2 text-xs">
              <div className="flex items-center gap-1.5 min-w-0 flex-1">
                <div className="h-5 w-5 sm:h-6 sm:w-6 overflow-hidden rounded-full shrink-0">
                  <AvatarFallback
                    name={uploaderName}
                    imageUrl={uploaderAvatar}
                    imageAlt={`${uploaderName} avatar`}
                  />
                </div>
                <span className="font-medium text-foreground truncate text-xs">{uploaderName}</span>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="theme-muted flex items-center gap-1 text-[11px]">
                  <Download className="h-3 w-3" />
                  {paper.download_count || 0}
                </span>
                {paper.solution_key && (
                  <Badge className="theme-status-badge--solution text-[9px] px-1.5 py-0 hover:bg-inherit">
                    <Star className="h-2.5 w-2.5 mr-0.5" />
                    Solution
                  </Badge>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

function FeaturedSingleResourceCard({
  item,
}: {
  item: { type: 'paper'; value: Paper } | { type: 'book'; value: Book };
}) {
  const paper = item.type === 'paper' ? item.value : null;
  const book = item.type === 'book' ? item.value : null;
  const to = paper ? `/paper/${paper.id}` : `/book/${book?.id}`;

  return (
    <div className="theme-highlight-card rounded-2xl p-5 shadow-lg border border-primary/25 bg-card/95 transition-all duration-300 hover:border-primary/50">
      <div className="grid grid-cols-1 sm:grid-cols-[140px_1fr] gap-4 items-center">
        <div>
          <DocumentCoverPreview
            title={item.value.title}
            courseCode={paper?.course_code || book?.courses?.[0]?.code}
            courseName={paper?.course_name || book?.courses?.[0]?.name}
            year={paper?.year || book?.publication_year}
            yearOfStudy={paper?.year_of_study || book?.year_of_study}
            semester={paper?.semester || book?.semester}
            paperType={paper?.paper_type || 'Exam'}
            department={paper?.department || book?.category || undefined}
            verificationStatus={paper?.verification_status}
            hasSolution={Boolean(paper?.solution_key)}
            isBook={item.type === 'book'}
            size="md"
          />
        </div>
        <div className="flex flex-col justify-between h-full space-y-3">
          <div>
            {/* Top badges bar */}
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
              <div className="flex items-center gap-1.5">
                <Badge className="theme-highlight-badge text-[11px] font-bold px-2.5 py-0.5 tracking-wide shadow-sm">
                  {paper ? '📄 PAST PAPER' : '📚 REFERENCE BOOK'}
                </Badge>
                {paper && <VerificationBadge status={paper.verification_status} />}
              </div>
              {(paper?.year_of_study || paper?.semester || book?.year_of_study || book?.semester) && (
                <span className="text-[11px] font-semibold text-primary bg-primary/10 px-2 py-0.5 rounded-full border border-primary/20">
                  {[paper?.year_of_study || book?.year_of_study, paper?.semester || book?.semester].filter(Boolean).join(' · ')}
                </span>
              )}
            </div>

            {/* Main Title */}
            <Link to={to} className="group block">
              <h3 className="text-base sm:text-lg font-bold text-foreground group-hover:text-primary transition-colors line-clamp-2">
                {item.value.title}
              </h3>
            </Link>
            <div className="space-y-1 text-xs text-muted-foreground mt-1.5">
              <p className="flex items-center gap-1.5 font-medium text-foreground/85">
                <BookOpen className="h-3.5 w-3.5 text-primary shrink-0" />
                <span className="line-clamp-1">
                  {paper ? `${paper.course_code} — ${paper.course_name}` : book?.authors.join(', ') || 'Academic reference book'}
                </span>
              </p>
              {paper?.department && (
                <p className="flex items-center gap-1.5">
                  <Clock className="h-3.5 w-3.5 text-muted-foreground/80 shrink-0" />
                  <span className="line-clamp-1">
                    {paper.department}
                  </span>
                </p>
              )}
            </div>
          </div>

          {/* Action and Download Stats Footer */}
          <div className="pt-3 border-t border-border/40 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <Download className="h-3.5 w-3.5 text-muted-foreground" />
                <span>{paper ? paper.download_count || 0 : book?.download_count || 0} downloads</span>
              </span>
              {paper?.solution_key && (
                <Badge className="theme-status-badge--solution text-[10px] hover:bg-inherit">
                  <Star className="h-3 w-3 mr-1" />
                  Has Solution
                </Badge>
              )}
            </div>

            <Link to={to}>
              <Button size="sm" className="theme-accent-bg text-xs h-8 px-3.5 gap-1.5 font-semibold shadow-sm hover:scale-[1.02] transition-transform">
                <span>Open {paper ? 'Paper' : 'Book'}</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

function HighlightResourceTile({
  item,
  delay,
}: {
  item: { type: 'paper'; value: Paper } | { type: 'book'; value: Book };
  delay: number;
}) {
  const paper = item.type === 'paper' ? item.value : null;
  const book = item.type === 'book' ? item.value : null;
  const to = paper ? `/paper/${paper.id}` : `/book/${book?.id}`;
  const studyMeta = [paper?.year_of_study || book?.year_of_study, paper?.semester || book?.semester].filter(Boolean).join(' · ');

  return (
    <Link to={to} className="block group h-full">
      <div
        className="theme-highlight-card resource-highlight-tile rounded-2xl p-3.5 cursor-pointer transition-all duration-300 hover:scale-[1.01] hover:border-primary/50 shadow-sm flex flex-col justify-between min-h-[6.8rem]"
        style={{ animationDelay: `${delay}ms` }}
      >
        <div>
          <div className="mb-1.5 flex items-center justify-between gap-1.5">
            <Badge className="theme-highlight-badge text-[9px] font-bold px-1.5 py-0.5">
              {paper ? '📄 PAPER' : '📚 BOOK'}
            </Badge>
            {studyMeta ? (
              <span className="text-[9px] font-semibold text-primary">{studyMeta}</span>
            ) : (
              paper && <VerificationBadge status={paper.verification_status} />
            )}
          </div>
          <h3 className="line-clamp-2 text-xs font-bold text-foreground group-hover:text-primary transition-colors">
            {item.value.title}
          </h3>
        </div>
        <div className="mt-2 space-y-0.5 border-t border-border/30 pt-1.5 text-[10px]">
          <p className="theme-highlight-muted line-clamp-1 font-medium">
            {paper ? `${paper.course_code} • ${paper.course_name}` : book?.authors?.join(', ') || 'Academic book'}
          </p>
          <div className="flex items-center justify-between theme-highlight-muted">
            <span>{paper ? `${paper.year} • ${paper.paper_type}` : `${book?.language || '—'}`}</span>
            <span className="font-semibold text-primary flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
              Open <ArrowRight className="h-2.5 w-2.5" />
            </span>
          </div>
        </div>
      </div>
    </Link>
  );
}

function BookPickCard({ book, uploaderProfiles }: { book: Book; uploaderProfiles?: Record<string, { profile?: any; imageUrl?: string | null }>; }) {
  const uploaderName = uploaderProfiles?.[book.uploaded_by]?.profile?.display_name || book.uploader_name || (book.uploaded_by ? `Contributor ${book.uploaded_by}` : 'Academic Contributor');
  const uploaderAvatar = uploaderProfiles?.[book.uploaded_by]?.imageUrl ?? (book.uploader_profile_picture_key || undefined);

  return (
    <Link to={`/book/${book.id}`} className="block group">
      <Card className="theme-panel h-full overflow-hidden border transition-all duration-300 hover:-translate-y-1 hover:shadow-lg flex flex-col justify-between">
        <div className="p-2.5 pb-0 sm:p-3 sm:pb-0">
          <DocumentCoverPreview
            title={book.title}
            courseCode={book.courses?.[0]?.code || undefined}
            courseName={book.courses?.[0]?.name || undefined}
            year={book.publication_year || new Date(book.created_at).getFullYear()}
            yearOfStudy={book.year_of_study}
            semester={book.semester}
            department={book.category || book.subject || 'Academic Reference'}
            isBook={true}
            size="md"
            className="group-hover:scale-[1.01] transition-transform"
          />
        </div>
        <CardContent className="p-2.5 pt-2 sm:p-3 sm:pt-2 flex flex-col justify-between flex-1 gap-1.5">
          <div>
            <div className="mb-1 flex flex-wrap items-center justify-between gap-1">
              <div className="flex flex-wrap items-center gap-1">
                <Badge variant="outline" className="border-primary text-[10px] sm:text-xs font-semibold text-primary px-1.5 py-0">
                  📚 BOOK
                </Badge>
                {(book.year_of_study || book.semester) && (
                  <Badge variant="secondary" className="text-[10px] sm:text-xs font-medium px-1.5 py-0">
                    {[book.year_of_study, book.semester].filter(Boolean).join(' · ')}
                  </Badge>
                )}
              </div>
              <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                {book.language?.toUpperCase() || 'REF'}
              </Badge>
            </div>
            <h3 className="theme-title mb-1 line-clamp-1 font-bold transition-colors group-hover:text-primary text-sm sm:text-base" title={book.title}>
              {book.title}
            </h3>
            <div className="theme-muted space-y-0.5 text-xs">
              <p className="truncate font-medium text-foreground/85">
                {book.authors.join(', ') || 'Author not specified'}
              </p>
              <p className="truncate text-muted-foreground">
                {book.courses?.map((item) => item.code || item.name).join(' · ') || book.category || 'Reference book'}
              </p>
              {book.modules && book.modules.length > 0 && (
                <p className="truncate text-muted-foreground">{book.modules.map((m) => m.name).join(' · ')}</p>
              )}
            </div>
          </div>
          <div>
            <div className="mt-1 pt-2 border-t border-border/40 flex items-center justify-between gap-2 text-xs">
              <div className="flex items-center gap-1.5 min-w-0 flex-1">
                <div className="h-5 w-5 sm:h-6 sm:w-6 overflow-hidden rounded-full shrink-0">
                  <AvatarFallback
                    name={uploaderName}
                    imageUrl={uploaderAvatar}
                    imageAlt={`${uploaderName} avatar`}
                  />
                </div>
                <span className="font-medium text-foreground truncate text-xs">{uploaderName}</span>
              </div>
              <span className="theme-muted flex items-center gap-1 text-[11px] shrink-0">
                <Download className="h-3 w-3" />
                {book.download_count || 0}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

function chooseHighlightResources(total: number, previous: number[] = []): number[] {
  if (total <= 0) return [];
  if (total === 1) return [0];
  if (total === 2) return [0, 1];
  const choices = Array.from({ length: total }, (_, index) => index)
    .sort(() => Math.random() - 0.5);
  const fresh = choices.filter((index) => !previous.includes(index));
  return [...fresh, ...choices].slice(0, Math.min(3, total));
}

export default function HomePage() {
  const { user } = useAuth();
  const [searchQuery, setSearchQuery] = useState('');
  const [papers, setPapers] = useState<Paper[]>([]);
  const [books, setBooks] = useState<Book[]>([]);
  const colleges = Array.from(new Set(papers.map((paper) => paper.college).filter(Boolean))).sort();
  const [personalized, setPersonalized] = useState<PersonalizedRecommendationsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [personalizedLoading, setPersonalizedLoading] = useState(false);
  const [stats, setStats] = useState({ total: 0, downloads: 0, verified: 0 });
  const [showOfflineBanner, setShowOfflineBanner] = useState(false);
  const [uploaderProfiles, setUploaderProfiles] = useState<Record<string, { profile?: any; imageUrl?: string | null }>>({});
  const [showPersonalizedOfflineBanner, setShowPersonalizedOfflineBanner] = useState(false);
  const [highlightSelections, setHighlightSelections] = useState<number[][]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    const cached = getCachedPaperListSnapshot();
    if (cached) {
      setShowOfflineBanner(cached.data_source === 'cache');
      setPapers(cached.items.filter((p) => !p.is_hidden));
      const totalDownloads = cached.items.reduce((sum, p) => sum + (p.download_count || 0), 0);
      const verifiedCount = cached.items.filter((p) => p.verification_status === 'verified').length;
      setStats({ total: cached.total, downloads: totalDownloads, verified: verifiedCount });
      setLoading(false);
    }
    loadPapers();
    void fetchBooks().then((data) => setBooks(data.items)).catch(() => setBooks([]));
  }, []);

  useEffect(() => {
    const ids = Array.from(new Set([
      ...papers.map((p) => p.user_id),
      ...(personalized?.recommended || []).map((p) => p.user_id),
      ...(personalized?.recently_viewed || []).map((p) => p.user_id),
      ...books.map((b) => b.uploaded_by),
    ].filter(Boolean)));
    if (ids.length === 0) return;
    let cancelled = false;
    (async () => {
      try {
        const resolved = await resolvePublicUserProfiles(ids);
        if (cancelled) return;
        const next: Record<string, { profile?: any; imageUrl?: string | null }> = {};
        for (const id of ids) {
          const r = resolved[id];
          if (r) {
            next[id] = { profile: r.profile || undefined, imageUrl: r.imageUrl || null };
          }
        }
        setUploaderProfiles((prev) => ({ ...prev, ...next }));
      } catch (e) {
        // ignore
      }
    })();
    return () => { cancelled = true; };
  }, [papers, personalized, books]);

  useEffect(() => {
    if (!user) {
      setPersonalized(null);
      setShowPersonalizedOfflineBanner(false);
      return;
    }
    const cached = getCachedPersonalizedRecommendationsSnapshot();
    if (cached) {
      setPersonalized({ ...cached, data_source: 'cache' });
      setShowPersonalizedOfflineBanner(true);
    }
    void loadPersonalizedRecommendations();
  }, [user]);

  const loadPapers = async () => {
    try {
      setLoading(true);
      const data = await fetchAllPapers({ sort: '-download_count', limit: 50 });
      setShowOfflineBanner(data.data_source === 'cache');
      setPapers(data.items.filter((p) => !p.is_hidden));
      const totalDownloads = data.items.reduce((sum, p) => sum + (p.download_count || 0), 0);
      const verifiedCount = data.items.filter((p) => p.verification_status === 'verified').length;
      setStats({ total: data.total, downloads: totalDownloads, verified: verifiedCount });
    } catch (err) {
      console.error('Failed to load papers:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadPersonalizedRecommendations = async () => {
    try {
      setPersonalizedLoading(true);
      const response = await fetchPersonalizedRecommendations();
      setPersonalized(response);
      setShowPersonalizedOfflineBanner(response?.data_source === 'cache');
    } catch (error) {
      console.error('Failed to load personalized recommendations:', error);
    } finally {
      setPersonalizedLoading(false);
    }
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      navigate(`/resources?q=${encodeURIComponent(searchQuery.trim())}`);
    } else {
      navigate('/resources');
    }
  };

  const trendingPapers = papers.slice(0, 6);
  const recentPapers = [...papers].sort((a, b) => {
    const dateA = a.created_at ? new Date(a.created_at).getTime() : 0;
    const dateB = b.created_at ? new Date(b.created_at).getTime() : 0;
    return dateB - dateA;
  }).slice(0, 6);
  const trendingBooks = [...books]
    .filter((book) => book.status === 'active' && book.visibility === 'public')
    .sort((a, b) => {
      const downloadDifference = (b.download_count || 0) - (a.download_count || 0);
      if (downloadDifference) return downloadDifference;
      const completenessDifference = Number(Boolean(b.cover_key)) + Number(Boolean(b.modules?.length)) - Number(Boolean(a.cover_key)) - Number(Boolean(a.modules?.length));
      if (completenessDifference) return completenessDifference;
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    })
    .slice(0, 6);
  const mixedResources = [
    ...papers.slice(0, 8).map((value) => ({ type: 'paper' as const, value })),
    ...books.slice(0, 8).map((value) => ({ type: 'book' as const, value })),
  ];
  const highlightRows = mixedResources.length
    ? (highlightSelections.length > 0
        ? highlightSelections
            .map((selection) => selection.map((index) => mixedResources[index]).filter(Boolean))
            .filter((row) => row.length > 0)
        : [mixedResources.slice(0, 3)])
    : [];
  const hasPersonalizedContent = Boolean(
    personalized && (personalized.recommended.length > 0 || personalized.recently_viewed.length > 0)
  );

  useEffect(() => {
    if (mixedResources.length === 0) {
      setHighlightSelections([]);
      return;
    }
    if (mixedResources.length === 1) {
      setHighlightSelections([[0]]);
      return;
    }
    if (mixedResources.length === 2) {
      setHighlightSelections([[0, 1]]);
      return;
    }
    const numRows = Math.min(3, Math.ceil(mixedResources.length / 3));
    setHighlightSelections(
      Array.from({ length: numRows }, () => chooseHighlightResources(mixedResources.length))
    );

    if (mixedResources.length > 3) {
      const timers = [3100, 4700, 6300].slice(0, numRows).map((duration, row) =>
        window.setInterval(() => {
          setHighlightSelections((selections) =>
            selections.map((selection, index) =>
              index === row ? chooseHighlightResources(mixedResources.length, selection) : selection
            )
          );
        }, duration)
      );
      return () => timers.forEach(window.clearInterval);
    }
  }, [mixedResources.length]);

  return (
    <div>
      {/* Hero Section */}
      <section className="theme-header theme-hero-section relative overflow-hidden">
        <div
          className="theme-hero-media absolute inset-0"
          style={{
            backgroundImage: `url(${HERO_IMAGE})`,
            backgroundSize: 'cover',
            backgroundPosition: 'center',
          }}
        />
        <div className="theme-hero-overlay absolute inset-0 pointer-events-none" />
        <div className="relative mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8 md:py-28"> 
          <div className="grid gap-10 lg:grid-cols-[1.08fr_0.92fr] lg:items-center">
            <div className="max-w-2xl">
              <h1 className="text-4xl font-bold leading-tight md:text-5xl">
                UR Academic
                <span className="theme-accent"> Resource Hub</span>
              </h1>
              <p className="theme-hero-copy mb-4 mt-4 text-lg">
                Access past papers, academic books, trusted solutions, and study support that helps University of Rwanda learners prepare faster and study smarter.
              </p>
             

              <form onSubmit={handleSearch} className="mb-8 flex flex-col sm:flex-row gap-2">
                <div className="relative flex-1">
                  <Search className="theme-muted absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2" />
                  <Input
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search papers, books, authors, course code, or year..."
                    className="theme-hero-input h-12 pl-10"
                  />
                </div>
                <Button type="submit" className="theme-accent-bg h-12 px-6 w-full sm:w-auto">
                  Search
                </Button>
              </form>

              <div className="mb-6 flex flex-wrap gap-2">
                {PAPER_TYPES.map((type) => (
                  <Button
                    key={type}
                    variant="outline"
                    size="sm"
                    onClick={() => navigate(`/resources?resource=paper&type=${type}`)}
                    className="theme-hero-filter text-xs"
                  >
                    {type}
                  </Button>
                ))}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => navigate('/resources?resource=book')}
                  className="theme-hero-filter text-xs"
                >
                  <BookOpen className="mr-1 h-3.5 w-3.5" />
                  Browse Resources
                </Button>
              </div>

              <div className="grid gap-3 text-sm sm:grid-cols-3">
                <div className="theme-hero-feature rounded-2xl px-4 py-3">
                  <p className="font-semibold">Fast revision</p>
                  <p className="theme-hero-feature-copy mt-1">Find common exam patterns and prepare with less guesswork.</p>
                </div>
                <div className="theme-hero-feature rounded-2xl px-4 py-3">
                  <p className="font-semibold">Trusted by peers</p>
                  <p className="theme-hero-feature-copy mt-1">Verified community uploads help strong material stand out.</p>
                </div>
                <div className="theme-hero-feature rounded-2xl px-4 py-3">
                  <p className="font-semibold">Study together</p>
                  <p className="theme-hero-feature-copy mt-1">Discussion, solutions, books, and AI support stay close to each resource.</p>
                </div>
              </div>
            </div>

            <div className="lg:justify-self-end w-full max-w-lg">
              <div className="theme-highlight-shell rounded-[2rem] p-5 sm:p-6 backdrop-blur-xl">
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.24em] text-primary">
                      {mixedResources.length === 1 ? 'Featured in Library' : 'Highlighted resources'}
                    </p>
                    <h2 className="mt-1 text-base sm:text-lg font-bold">
                      {mixedResources.length === 1 ? 'Active Exam Paper' : 'What students are opening most'}
                    </h2>
                  </div>
                  <Badge className="theme-highlight-stat shrink-0 hover:bg-transparent gap-1.5 px-2.5 py-1">
                    <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                    <span>Live picks</span>
                  </Badge>
                </div>

                {loading && !mixedResources.length ? (
                  <div className="theme-highlight-card flex flex-col justify-center gap-3 rounded-[1.6rem] p-5">
                    <div className="h-16 animate-pulse rounded-2xl bg-muted/60" />
                    <div className="h-16 animate-pulse rounded-2xl bg-muted/40" />
                  </div>
                ) : mixedResources.length === 1 ? (
                  <FeaturedSingleResourceCard item={mixedResources[0]} />
                ) : highlightRows.length ? (
                  <div className="resource-highlight-viewport" aria-live="polite">
                    <div className="space-y-2.5">
                      {highlightRows.map((row, rowIndex) => (
                        <div
                          key={`highlight-row-${rowIndex}`}
                          className={`resource-highlight-grid ${
                            row.length === 2 ? 'grid-cols-2' : 'grid-cols-1 sm:grid-cols-2 md:grid-cols-3'
                          }`}
                        >
                          {row.map((item, columnIndex) => (
                            <HighlightResourceTile
                              key={`${item.type}-${item.value.id}-${rowIndex}-${columnIndex}`}
                              item={item}
                              delay={rowIndex * 110 + columnIndex * 55}
                            />
                          ))}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="theme-highlight-card flex flex-col items-center justify-center rounded-[1.6rem] p-6 text-center space-y-3">
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                      <BookOpen className="h-6 w-6" />
                    </div>
                    <div className="space-y-1 max-w-xs">
                      <p className="text-sm font-bold text-foreground">No resources available yet</p>
                      <p className="theme-highlight-muted text-xs leading-relaxed">
                        Uploaded past papers and books will automatically show up here as live student picks.
                      </p>
                    </div>
                    <Button size="sm" onClick={() => navigate('/upload')} className="theme-accent-bg text-xs">
                      <Upload className="h-3.5 w-3.5 mr-1.5" />
                      Upload First Paper
                    </Button>
                  </div>
                )}

                {/* Library Summary Footer */}
                {mixedResources.length > 0 && (
                  <div className="mt-4 pt-3.5 border-t border-border/40 flex items-center justify-between text-xs">
                    <span className="theme-highlight-muted flex items-center gap-1.5 font-medium">
                      <span>{papers.length} {papers.length === 1 ? 'Paper' : 'Papers'}{books.length ? ` · ${books.length} Books` : ''} in Library</span>
                    </span>
                    <Link to="/resources" className="font-semibold text-primary hover:underline flex items-center gap-1">
                      <span>Browse All</span>
                      <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      {user && (
        <section className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
          {showPersonalizedOfflineBanner && (
            <div className="mb-5">
              <OfflineDataBanner message="Personalized recommendations are using cached data because the network is slow or unavailable." />
            </div>
          )}

          <div className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="theme-link-accent text-xs font-semibold uppercase tracking-[0.28em]">For you</p>
              <h2 className="theme-title mt-2 text-1xl font-bold">Personalized paper picks</h2>
              <p className="theme-muted mt-2 max-w-2xl text-sm">
                We use your recent opens and downloads to suggest papers with similar course, department, lecturer, and paper-type patterns.
              </p>
            </div>
            <Button variant="outline" onClick={() => void loadPersonalizedRecommendations()} disabled={personalizedLoading}>
              {personalizedLoading ? 'Refreshing...' : 'Refresh suggestions'}
            </Button>
          </div>

          {personalizedLoading && !hasPersonalizedContent ? (
            <div className="grid gap-4 md:grid-cols-3">
              {[1, 2, 3].map((item) => (
                <div key={item} className="h-40 animate-pulse rounded-2xl bg-muted" />
              ))}
            </div>
          ) : hasPersonalizedContent ? (
            <div className="space-y-8">
              {(personalized?.top_departments?.length || personalized?.top_paper_types?.length || personalized?.top_course_codes?.length) ? (
                <div className="theme-soft-panel rounded-3xl p-5">
                  <p className="theme-title text-sm font-semibold">You mostly read</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {(personalized?.top_departments || []).map((item) => (
                      <Badge key={`dept-${item}`} variant="secondary">{item}</Badge>
                    ))}
                    {(personalized?.top_paper_types || []).map((item) => (
                      <Badge key={`type-${item}`} variant="secondary">{item}</Badge>
                    ))}
                    {(personalized?.top_course_codes || []).map((item) => (
                      <Badge key={`course-${item}`} className="theme-status-badge--solution hover:bg-inherit">{item}</Badge>
                    ))}
                  </div>
                </div>
              ) : null}

              {personalized?.recommended?.length ? (
                <div>
                  <div className="mb-4 flex items-center justify-between">
                    <h3 className="theme-title text-xl font-semibold">Recommended for you</h3>
                    <Button variant="ghost" onClick={() => navigate('/resources')}>Browse all resources</Button>
                  </div>
                  <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
                    {personalized.recommended.slice(0, 6).map((paper) => (
                      <PaperCard key={`recommended-${paper.id}`} paper={paper} uploaderProfiles={uploaderProfiles} />
                    ))}
                  </div>
                </div>
              ) : null}

              {personalized?.recently_viewed?.length ? (
                <div>
                  <div className="mb-4 flex items-center justify-between">
                    <h3 className="theme-title text-xl font-semibold">Recently opened</h3>
                    <Button variant="ghost" onClick={() => navigate('/dashboard')}>Open dashboard</Button>
                  </div>
                  <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
                    {personalized.recently_viewed.slice(0, 6).map((paper) => (
                      <PaperCard key={`recent-${paper.id}`} paper={paper} uploaderProfiles={uploaderProfiles} />
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="theme-soft-panel rounded-3xl p-6 text-sm text-muted-foreground">
              Open a few papers and we will start suggesting similar ones.
            </div>
          )}
        </section>
      )}

      {/* Stats Bar */}
      <section className="theme-section-band shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          {showOfflineBanner && (
            <OfflineDataBanner message="You are seeing cached homepage stats and paper lists while live data is unavailable." />
          )}
          <div className="grid grid-cols-2 gap-8 sm:grid-cols-4">
            <div className="text-center">
              <div className="flex items-center justify-center gap-2 mb-1">
                <FileText className="theme-accent h-5 w-5" />
                <span className="theme-title text-1xl font-bold">{stats.total}</span>
              </div>
              <p className="theme-muted text-sm">Total Papers</p>
            </div>
            <div className="text-center">
              <div className="flex items-center justify-center gap-2 mb-1">
                <Download className="theme-accent h-5 w-5" />
                <span className="theme-title text-1xl font-bold">{stats.downloads.toLocaleString()}</span>
              </div>
              <p className="theme-muted text-sm">Total Downloads</p>
            </div>
            <div className="text-center">
              <div className="flex items-center justify-center gap-2 mb-1">
                <CheckCircle className="h-5 w-5 text-success" />
                <span className="theme-title text-1xl font-bold">{stats.verified}</span>
              </div>
              <p className="theme-muted text-sm">Verified Papers</p>
            </div>
            <div className="text-center">
              <div className="flex items-center justify-center gap-2 mb-1">
                <BookOpen className="theme-accent h-5 w-5" />
                <span className="theme-title text-1xl font-bold">{books.length}</span>
              </div>
              <p className="theme-muted text-sm">Academic Books</p>
            </div>
          </div>
        </div>
      </section>

      {/* Browse by College */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <h2 className="theme-title mb-6 text-1xl font-bold">Browse by College</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {colleges.map((college) => (
            <Link key={college} to={`/resources?college=${encodeURIComponent(college)}`} className="block">
              <Card className="theme-panel border transition-all duration-300 hover:-translate-y-0.5 hover:shadow-md">
                <CardContent className="p-4 flex items-center justify-between">
                  <span className="theme-title text-sm font-medium">{college}</span>
                  <ArrowRight className="theme-accent h-4 w-4" />
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </section>

      {/* Trending Papers */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <TrendingUp className="theme-accent h-6 w-6" />
            <h2 className="theme-title text-1xl font-bold">Trending Papers</h2>
          </div>
          <Button variant="ghost" asChild className="theme-accent hover:text-primary">
            <Link to="/resources?resource=paper">View All <ArrowRight className="ml-1 h-4 w-4" /></Link>
          </Button>
        </div>
        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {[1, 2, 3].map((i) => (
              <Card key={i} className="theme-panel animate-pulse">
                <CardContent className="p-5 space-y-3">
                  <div className="h-4 w-1/3 rounded bg-muted" />
                  <div className="h-5 w-full rounded bg-muted" />
                  <div className="h-4 w-2/3 rounded bg-muted" />
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {trendingPapers.map((paper) => (
              <PaperCard key={paper.id} paper={paper} uploaderProfiles={uploaderProfiles} />
            ))}
          </div>
        )}
      </section>

      {trendingBooks.length > 0 && (
        <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-2">
              <BookOpen className="theme-accent h-6 w-6" />
              <div>
                <h2 className="theme-title text-1xl font-bold">Trending Books</h2>
                <p className="theme-muted text-sm">Ranked by downloads, complete book details, and recent additions.</p>
              </div>
            </div>
            <Button variant="ghost" asChild className="theme-accent hover:text-primary">
              <Link to="/resources?resource=book">View All <ArrowRight className="ml-1 h-4 w-4" /></Link>
            </Button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {trendingBooks.map((book) => <BookPickCard key={book.id} book={book} uploaderProfiles={uploaderProfiles} />)}
          </div>
        </section>
      )}

      {/* Recent Papers */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <Clock className="theme-accent h-6 w-6" />
            <h2 className="theme-title text-1xl font-bold">Recently Added Papers</h2>
          </div>
          <Button variant="ghost" asChild className="theme-accent hover:text-primary">
            <Link to="/resources?resource=paper&sort=-created_at">View All <ArrowRight className="ml-1 h-4 w-4" /></Link>
          </Button>
        </div>
        {!loading && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {recentPapers.map((paper) => (
              <PaperCard key={paper.id} paper={paper} uploaderProfiles={uploaderProfiles} />
            ))}
          </div>
        )}
      </section>

      

      <section className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <ExpandableContentSection
          title="University of Rwanda academic resources students can trust"
          summary="Open this section to learn how the hub organizes UR past papers, academic books, and study materials for faster revision."
          expandLabel="Open overview"
          collapseLabel="Hide overview"
        >
          <p className="theme-muted text-base leading-8">
            UR Academic Resource Hub is designed to make <strong>University of Rwanda past papers</strong>, academic books, revision materials, and peer-reviewed learning resources easier to find in one place. Instead of depending on scattered chats, disappearing links, and unstructured class archives, students can browse one searchable hub for <strong>UR exam papers</strong>, assignments, CATs, course books, and related solution notes. Papers remain organized by course code, course name, department, academic year, paper type, and download popularity, while books provide author, language, edition, and course context.
          </p>
          <p className="theme-muted text-base leading-8">
            The platform also supports stronger study decisions. Learners can compare the most downloaded papers, discover relevant academic books, filter by college, and identify materials that already helped other students prepare. That makes the site useful not only as a file library, but also as a practical guide for faster revision. When students search for <strong>study materials Rwanda</strong> universities rarely centralize well, they need relevant context, not just filenames. This homepage is built to explain that value clearly so visitors and search engines both understand what the site offers.
          </p>
          <p className="theme-muted text-base leading-8">
            If you want to start quickly, go straight to the <Link to="/resources" className="theme-link-accent font-medium">resource browser</Link> to search papers and books by keyword, course, author, and year. If you want to understand the mission behind the platform, visit the <Link to="/student-stories" className="theme-link-accent font-medium">student stories and study tips page</Link>. The goal is simple: keep high-value academic content indexable, searchable, and genuinely useful for University of Rwanda learners preparing for exams.
          </p>
        </ExpandableContentSection>
      </section>
    </div>
  );
}
