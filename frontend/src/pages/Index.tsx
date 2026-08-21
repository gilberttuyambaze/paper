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
  return (
    <Link to={`/paper/${paper.id}`} className="block">
      <Card className="theme-panel group border transition-all duration-300 hover:-translate-y-1 hover:shadow-lg">
        <CardContent className="p-5">
          <div className="flex items-start justify-between mb-3">
            <Badge variant="outline" className="border-primary text-xs font-medium text-primary">
              {paper.paper_type}
            </Badge>
            <VerificationBadge status={paper.verification_status} />
          </div>
          <h3 className="theme-title mb-2 line-clamp-2 font-semibold transition-colors group-hover:text-primary">
            {paper.title}
          </h3>
          <div className="theme-muted space-y-1 text-sm">
            <p className="flex items-center gap-1">
              <BookOpen className="h-3.5 w-3.5" />
              {paper.course_code} - {paper.course_name}
            </p>
            <p className="flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" />
              {paper.year} - {paper.department}
            </p>
          </div>
          <div className="mt-4 flex items-center justify-between border-t pt-3">
            <span className="theme-muted flex items-center gap-1 text-xs">
              <Download className="h-3.5 w-3.5" />
              {paper.download_count || 0} downloads
            </span>
            {paper.solution_key && (
              <Badge className="theme-status-badge--solution text-xs hover:bg-inherit">
                <Star className="h-3 w-3 mr-1" />
                Has Solution
              </Badge>
            )}
          </div>
          <div className="mt-3 flex items-center gap-3">
            <div className="h-8 w-8 overflow-hidden rounded-full">
              <AvatarFallback
                name={uploaderProfiles?.[paper.user_id]?.profile?.display_name || paper.uploader_display_name || `Uploader ${paper.user_id}`}
                imageUrl={uploaderProfiles?.[paper.user_id]?.imageUrl ?? undefined}
                imageAlt={`${uploaderProfiles?.[paper.user_id]?.profile?.display_name || paper.uploader_display_name || 'Uploader'} avatar`}
              />
            </div>
            <div className="text-xs theme-muted">
              <div className="font-medium text-sm">{uploaderProfiles?.[paper.user_id]?.profile?.display_name || paper.uploader_display_name || `Uploader ${paper.user_id}`}</div>
              <div>{paper.course_code} · {paper.year}</div>
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

function HighlightResourceTile({ item, delay }: { item: { type: 'paper'; value: Paper } | { type: 'book'; value: Book }; delay: number }) {
  const paper = item.type === 'paper' ? item.value : null;
  const book = item.type === 'book' ? item.value : null;
  return <div className="theme-highlight-card resource-highlight-tile rounded-xl p-3" style={{ animationDelay: `${delay}ms` }}>
    <div className="mb-2 flex items-center justify-between gap-1"><Badge className="theme-highlight-badge text-[9px]">{paper ? '📄 PAPER' : '📚 BOOK'}</Badge>{paper && <VerificationBadge status={paper.verification_status} />}</div>
    <h3 className="line-clamp-2 text-xs font-semibold">{item.value.title}</h3>
    <p className="theme-highlight-muted mt-2 line-clamp-2 text-[10px]">{paper ? `${paper.course_code} • ${paper.course_name}` : book?.authors.join(', ') || 'Academic book'}</p>
    <p className="theme-highlight-muted mt-1 text-[10px]">{paper ? `${paper.year} • ${paper.paper_type}` : `${book?.language || '—'}${book?.edition ? ` • ${book.edition}` : ''}`}</p>
  </div>;
}

function BookPickCard({ book }: { book: Book }) {
  return (
    <Link to={`/resources?resource=book&q=${encodeURIComponent(book.title)}`} className="block">
      <Card className="theme-panel group border transition-all duration-300 hover:-translate-y-1 hover:shadow-lg">
        <CardContent className="p-5">
          <div className="mb-3 flex items-start justify-between">
            <Badge variant="outline" className="border-primary text-xs font-medium text-primary">📚 BOOK</Badge>
            <BookOpen className="theme-accent h-5 w-5" />
          </div>
          <h3 className="theme-title mb-2 line-clamp-2 font-semibold transition-colors group-hover:text-primary">{book.title}</h3>
          <div className="theme-muted space-y-1 text-sm">
            <p className="line-clamp-1">{book.authors.join(', ') || 'Author not specified'}</p>
            <p className="line-clamp-1">{book.language || 'Language not specified'}{book.edition ? ` · ${book.edition}` : ''}</p>
            <p className="line-clamp-1">{book.modules?.map((module) => module.name).join(' · ') || 'Course reference book'}</p>
          </div>
          <div className="mt-4 flex items-center justify-between border-t pt-3">
            <span className="theme-muted flex items-center gap-1 text-xs"><Download className="h-3.5 w-3.5" />{book.download_count || 0} downloads</span>
            <span className="text-xs font-medium text-primary">Browse book</span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

function chooseHighlightResources(total: number, previous: number[] = []): number[] {
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
  const [highlightSelections, setHighlightSelections] = useState<number[][]>([[], [], []]);
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
    const ids = Array.from(new Set([...papers.slice(0, 4), ...trendingPapers, ...recentPapers].map((p) => p.user_id)));
    if (ids.length === 0) return;
    let cancelled = false;
    (async () => {
      try {
        const resolved = await resolvePublicUserProfiles(ids);
        if (cancelled) return;
        const next: Record<string, { profile?: any; imageUrl?: string | null }> = {};
        for (const id of ids) {
          const r = resolved[id];
          next[id] = { profile: r.profile || undefined, imageUrl: r.imageUrl || null };
        }
        setUploaderProfiles(next);
      } catch (e) {
        // ignore
      }
    })();
    return () => { cancelled = true; };
  }, [papers]);

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
    ? highlightSelections.map((selection) => selection.map((index) => mixedResources[index]).filter(Boolean))
    : [];
  const hasPersonalizedContent = Boolean(
    personalized && (personalized.recommended.length > 0 || personalized.recently_viewed.length > 0)
  );

  useEffect(() => {
    if (mixedResources.length < 2) return;
    setHighlightSelections([
      chooseHighlightResources(mixedResources.length),
      chooseHighlightResources(mixedResources.length),
      chooseHighlightResources(mixedResources.length),
    ]);
    const timers = [3100, 4700, 6300].map((duration, row) => window.setInterval(() => {
      setHighlightSelections((selections) => selections.map((selection, index) => (
        index === row ? chooseHighlightResources(mixedResources.length, selection) : selection
      )));
    }, duration));
    return () => timers.forEach(window.clearInterval);
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
        <div className="relative mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8 md:py-28"> 
          <div className="grid gap-10 lg:grid-cols-[1.08fr_0.92fr] lg:items-center">
            <div className="max-w-2xl">
              <h1 className="text-4xl font-bold leading-tight md:text-5xl">
                UR Academic
                <span className="theme-accent"> Resource Hub</span>
              </h1>
              <p className="theme-hero-copy mb-4 mt-4 text-lg">
                Access past papers, academic books, trusted solutions, and study support that helps University of Rwanda learners prepare faster and study smarter.
              </p>
              <p className="theme-hero-copy mb-8 max-w-xl text-sm leading-6">
                Search past papers and course books, discover lecturer-linked material, and learn from a growing community that keeps useful content visible.
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
                  Browse Books
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

            <div className="lg:justify-self-end">
              <div className="theme-highlight-shell rounded-[2rem] p-6 backdrop-blur-xl">
                <div className="mb-5 flex items-center justify-between">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.28em] text-primary">Highlighted resources</p>
                    <h2 className="mt-2 text-2xl font-bold">What students are opening most</h2>
                  </div>
                  <Badge className="theme-highlight-stat shrink-0 hover:bg-transparent">Live picks</Badge>
                </div>

                {highlightRows.length ? (
                  <div className="resource-highlight-viewport" aria-live="polite">
                    <div className="space-y-2">
                      {highlightRows.map((row, rowIndex) => (
                        <div key={`highlight-row-${rowIndex}`} className="resource-highlight-grid">
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
                  <div className="theme-highlight-card flex h-[22rem] items-center justify-center rounded-[1.6rem] p-5 text-center">
                    <p className="theme-highlight-muted text-sm">Highlighted papers and books will appear here as soon as the library loads.</p>
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
              <h2 className="theme-title mt-2 text-2xl font-bold">Personalized paper picks</h2>
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
                    <Button variant="ghost" onClick={() => navigate('/past-papers')}>Browse all</Button>
                  </div>
                  <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
                    {personalized.recommended.slice(0, 6).map((paper) => (
                      <PaperCard key={`recommended-${paper.id}`} paper={paper} />
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
                      <PaperCard key={`recent-${paper.id}`} paper={paper} />
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
                <span className="theme-title text-2xl font-bold">{stats.total}</span>
              </div>
              <p className="theme-muted text-sm">Total Papers</p>
            </div>
            <div className="text-center">
              <div className="flex items-center justify-center gap-2 mb-1">
                <Download className="theme-accent h-5 w-5" />
                <span className="theme-title text-2xl font-bold">{stats.downloads.toLocaleString()}</span>
              </div>
              <p className="theme-muted text-sm">Total Downloads</p>
            </div>
            <div className="text-center">
              <div className="flex items-center justify-center gap-2 mb-1">
                <CheckCircle className="h-5 w-5 text-success" />
                <span className="theme-title text-2xl font-bold">{stats.verified}</span>
              </div>
              <p className="theme-muted text-sm">Verified Papers</p>
            </div>
            <div className="text-center">
              <div className="flex items-center justify-center gap-2 mb-1">
                <BookOpen className="theme-accent h-5 w-5" />
                <span className="theme-title text-2xl font-bold">{books.length}</span>
              </div>
              <p className="theme-muted text-sm">Academic Books</p>
            </div>
          </div>
        </div>
      </section>

      {/* Browse by College */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <h2 className="theme-title mb-6 text-2xl font-bold">Browse by College</h2>
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
            <h2 className="theme-title text-2xl font-bold">Trending Papers</h2>
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
              <PaperCard key={paper.id} paper={paper} />
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
                <h2 className="theme-title text-2xl font-bold">Trending Books</h2>
                <p className="theme-muted text-sm">Ranked by downloads, complete book details, and recent additions.</p>
              </div>
            </div>
            <Button variant="ghost" asChild className="theme-accent hover:text-primary">
              <Link to="/resources?resource=book">View All <ArrowRight className="ml-1 h-4 w-4" /></Link>
            </Button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {trendingBooks.map((book) => <BookPickCard key={book.id} book={book} />)}
          </div>
        </section>
      )}

      {/* Recent Papers */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <Clock className="theme-accent h-6 w-6" />
            <h2 className="theme-title text-2xl font-bold">Recently Added Papers</h2>
          </div>
          <Button variant="ghost" asChild className="theme-accent hover:text-primary">
            <Link to="/resources?resource=paper&sort=-created_at">View All <ArrowRight className="ml-1 h-4 w-4" /></Link>
          </Button>
        </div>
        {!loading && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {recentPapers.map((paper) => (
              <PaperCard key={paper.id} paper={paper} />
            ))}
          </div>
        )}
      </section>

      {/* CTA Section */}
      <section className="theme-header theme-cta-section relative mt-8 overflow-hidden">
        <div
          className="theme-cta-media absolute inset-0"
          style={{
            backgroundImage: `url(${COLLAB_IMAGE})`,
            backgroundSize: 'cover',
            backgroundPosition: 'center',
          }}
        />
        <div className="theme-cta-overlay absolute inset-0 pointer-events-none" />
        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 text-center">
          <h2 className="text-3xl font-bold mb-4">Contribute to the Community</h2>
          <p className="theme-cta-copy mx-auto mb-8 max-w-xl">
            Share past papers, academic books, and solutions to help fellow students. Every contribution makes a difference.
          </p>
          <Button
            onClick={() => navigate('/upload')}
            className="theme-accent-bg px-8 py-3 text-lg"
            size="lg"
          >
            <Upload className="mr-2 h-5 w-5" />
            Upload a Resource
          </Button>
        </div>
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
