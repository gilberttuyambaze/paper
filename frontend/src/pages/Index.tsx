import { useState, useEffect, useMemo } from 'react';
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
  ChevronLeft,
  ChevronRight,
  Flame,
} from 'lucide-react';

const HERO_IMAGE = '/assets/illustrations/landing.jpg';
const COLLAB_IMAGE = '/assets/illustrations/peer-collaboration.svg';

const PAPER_TYPES = ['Exam', 'CAT', 'Assignment', 'GroupWork'];

function VerificationBadge({ status }: { status?: string }) {
  if (status === 'verified') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100/90 dark:bg-emerald-950/60 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-800 dark:text-emerald-300">
        <CheckCircle className="h-3 w-3" />
        Verified
      </span>
    );
  }
  if (status === 'community') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-100/90 dark:bg-amber-950/60 px-2.5 py-0.5 text-[11px] font-semibold text-amber-800 dark:text-amber-300">
        <Users className="h-3 w-3" />
        Community
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
      Unverified
    </span>
  );
}

function PaperCard({ paper, uploaderProfiles }: { paper: Paper; uploaderProfiles?: Record<string, { profile?: any; imageUrl?: string | null }>; }) {
  const uploaderName = uploaderProfiles?.[paper.user_id]?.profile?.display_name || paper.uploader_display_name || (paper.user_id ? `Contributor ${paper.user_id}` : 'Academic Contributor');
  const uploaderAvatar = uploaderProfiles?.[paper.user_id]?.imageUrl ?? (paper.uploader_profile_picture_key || undefined);

  return (
    <Link to={`/paper/${paper.id}`} className="block group h-full focus:outline-none">
      <Card className="theme-panel h-full overflow-hidden rounded-2xl border border-border/70 hover:border-primary/50 transition-all duration-300 hover:-translate-y-1 hover:shadow-lg flex flex-col justify-between">
        <div className="p-3 pb-0">
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
        <CardContent className="p-3 pt-2.5 flex flex-col justify-between flex-1 gap-2">
          <div>
            <div className="flex items-center justify-between gap-1.5 mb-1.5">
              <span className="inline-flex items-center rounded-full border border-orange-400/60 bg-orange-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-orange-700 dark:text-orange-400">
                {paper.paper_type || 'Exam'}
              </span>

              <div className="flex items-center gap-1">
                <VerificationBadge status={paper.verification_status} />
                {paper.solution_key && (
                  <span className="inline-flex items-center gap-0.5 rounded-full bg-amber-100/90 dark:bg-amber-950/60 px-2 py-0.5 text-[10px] font-bold text-amber-800 dark:text-amber-300">
                    <Star className="h-2.5 w-2.5 fill-amber-500 text-amber-500" />
                    Solved
                  </span>
                )}
              </div>
            </div>

            <h3 className="line-clamp-1 text-sm sm:text-base font-bold text-foreground group-hover:text-primary transition-colors leading-snug" title={paper.title}>
              {paper.title}
            </h3>

            <div className="mt-1 space-y-0.5 text-xs text-muted-foreground">
              <p className="flex items-center gap-1.5 font-medium text-foreground/85 truncate">
                <BookOpen className="h-3.5 w-3.5 text-amber-600 dark:text-amber-500 shrink-0" />
                <span className="truncate">{paper.course_code ? `${paper.course_code} - ` : ''}{paper.course_name || 'Academic Course'}</span>
              </p>
              <p className="flex items-center gap-1.5 truncate text-muted-foreground">
                <Clock className="h-3.5 w-3.5 text-muted-foreground/70 shrink-0" />
                <span className="truncate">{paper.year ? `${paper.year} · ` : ''}{paper.department || 'University of Rwanda'}</span>
              </p>
            </div>
          </div>

          <div className="pt-2 border-t border-border/50 flex items-center justify-between gap-2 text-xs">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <div className="h-6 w-6 overflow-hidden rounded-full shrink-0 border border-border/40">
                <AvatarFallback
                  name={uploaderName}
                  imageUrl={uploaderAvatar}
                  imageAlt={`${uploaderName} avatar`}
                />
              </div>
              <span className="font-semibold text-foreground/90 truncate text-xs">{uploaderName}</span>
            </div>
            <div className="flex items-center gap-1 text-muted-foreground text-xs shrink-0">
              <Download className="h-3.5 w-3.5 text-muted-foreground/70" />
              <span>{paper.download_count || 0}</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

function HighlightResourceTile({
  item,
  uploaderProfiles,
}: {
  item: { type: 'paper'; value: Paper } | { type: 'book'; value: Book };
  uploaderProfiles?: Record<string, { profile?: any; imageUrl?: string | null }>;
}) {
  const paper = item.type === 'paper' ? item.value : null;
  const book = item.type === 'book' ? item.value : null;
  const to = paper ? `/paper/${paper.id}` : `/book/${book?.id}`;
  const uploaderId = paper ? paper.user_id : book?.uploaded_by;
  const fallbackName = paper ? paper.uploader_display_name : book?.uploader_name;
  const uploaderName = uploaderProfiles?.[uploaderId || '']?.profile?.display_name || fallbackName || (uploaderId ? `Contributor ${uploaderId}` : 'Academic Contributor');
  const uploaderAvatar = uploaderProfiles?.[uploaderId || '']?.imageUrl ?? (paper?.uploader_profile_picture_key || book?.uploader_profile_picture_key || undefined);
  const downloadCount = paper ? paper.download_count || 0 : book?.download_count || 0;
  const year = paper ? paper.year : (book?.publication_year || (book?.created_at ? new Date(book.created_at).getFullYear() : ''));
  const departmentOrCategory = paper ? (paper.department || 'Applied Science') : (book?.category || book?.subject || 'Academic Reference');
  const courseCode = paper ? paper.course_code : book?.courses?.[0]?.code;
  const courseName = paper ? paper.course_name : (book?.courses?.[0]?.name || book?.authors?.join(', '));
  const typeLabel = paper ? (paper.paper_type || 'Exam') : 'Book';

  return (
    <Link to={to} className="block group h-full focus:outline-none">
      <Card className="theme-panel h-full overflow-hidden rounded-2xl border border-border/70 hover:border-primary/50 transition-all duration-300 hover:-translate-y-1 hover:shadow-lg flex flex-col justify-between bg-card dark:bg-card/95">
        <div className="p-3 pb-0">
          <DocumentCoverPreview
            title={item.value.title}
            courseCode={courseCode}
            courseName={courseName}
            year={year}
            yearOfStudy={paper?.year_of_study || book?.year_of_study}
            semester={paper?.semester || book?.semester}
            paperType={paper?.paper_type || 'Exam'}
            department={departmentOrCategory}
            verificationStatus={paper?.verification_status}
            hasSolution={Boolean(paper?.solution_key)}
            isBook={item.type === 'book'}
            size="md"
            className="group-hover:scale-[1.01] transition-transform"
          />
        </div>
        <CardContent className="p-3 pt-2.5 flex flex-col justify-between flex-1 gap-2">
          <div>
            {/* Top badges row matching reference image */}
            <div className="flex items-center justify-between gap-1.5 mb-1.5">
              {paper ? (
                <span className="inline-flex items-center rounded-full border border-orange-400/60 bg-orange-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-orange-700 dark:text-orange-400">
                  {typeLabel}
                </span>
              ) : (
                <span className="inline-flex items-center rounded-full border border-purple-500/50 bg-purple-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-purple-700 dark:text-purple-400">
                  📚 Book
                </span>
              )}

              <div className="flex items-center gap-1">
                {paper ? (
                  <VerificationBadge status={paper.verification_status} />
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-full bg-amber-100/90 dark:bg-amber-950/60 px-2.5 py-0.5 text-[11px] font-semibold text-amber-800 dark:text-amber-300">
                    <Users className="h-3 w-3" />
                    Community
                  </span>
                )}
                {paper?.solution_key && (
                  <span className="inline-flex items-center gap-0.5 rounded-full bg-amber-100/90 dark:bg-amber-950/60 px-2 py-0.5 text-[10px] font-bold text-amber-800 dark:text-amber-300">
                    <Star className="h-2.5 w-2.5 fill-amber-500 text-amber-500" />
                    Solved
                  </span>
                )}
              </div>
            </div>

            {/* Title */}
            <h3 className="line-clamp-1 text-sm sm:text-base font-bold text-foreground group-hover:text-primary transition-colors leading-snug" title={item.value.title}>
              {item.value.title}
            </h3>

            {/* Course & Meta details */}
            <div className="mt-1 space-y-0.5 text-xs text-muted-foreground">
              <p className="flex items-center gap-1.5 font-medium text-foreground/85 truncate">
                <BookOpen className="h-3.5 w-3.5 text-amber-600 dark:text-amber-500 shrink-0" />
                <span className="truncate">
                  {courseCode ? `${courseCode} - ` : ''}{courseName || 'Academic Course'}
                </span>
              </p>
              <p className="flex items-center gap-1.5 truncate text-muted-foreground">
                <Clock className="h-3.5 w-3.5 text-muted-foreground/70 shrink-0" />
                <span className="truncate">
                  {year ? `${year} · ` : ''}{departmentOrCategory || 'University of Rwanda'}
                </span>
              </p>
            </div>
          </div>

          {/* Footer row */}
          <div className="pt-2 border-t border-border/50 flex items-center justify-between gap-2 text-xs">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <div className="h-6 w-6 overflow-hidden rounded-full shrink-0 border border-border/40">
                <AvatarFallback
                  name={uploaderName}
                  imageUrl={uploaderAvatar}
                  imageAlt={`${uploaderName} avatar`}
                />
              </div>
              <span className="font-semibold text-foreground/90 truncate text-xs">{uploaderName}</span>
            </div>
            <div className="flex items-center gap-1 text-muted-foreground text-xs shrink-0">
              <Download className="h-3.5 w-3.5 text-muted-foreground/70" />
              <span>{downloadCount}</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

type HighlightTab = 'all' | 'papers' | 'books' | 'solved';

function HighlightedResourcesShowcase({
  papers,
  books,
  loading,
  uploaderProfiles,
}: {
  papers: Paper[];
  books: Book[];
  loading: boolean;
  uploaderProfiles?: Record<string, { profile?: any; imageUrl?: string | null }>;
}) {
  const [activeTab, setActiveTab] = useState<HighlightTab>('all');
  const [currentPage, setCurrentPage] = useState(0);
  const [isHovered, setIsHovered] = useState(false);
  const navigate = useNavigate();

  const allMixed = useMemo(() => {
    const list: ({ type: 'paper'; value: Paper } | { type: 'book'; value: Book })[] = [];
    const maxLen = Math.max(papers.length, books.length);
    for (let i = 0; i < maxLen; i++) {
      if (i < papers.length) list.push({ type: 'paper', value: papers[i] });
      if (i < books.length) list.push({ type: 'book', value: books[i] });
    }
    return list;
  }, [papers, books]);

  const filteredItems = useMemo(() => {
    switch (activeTab) {
      case 'papers':
        return papers.map((p) => ({ type: 'paper' as const, value: p }));
      case 'books':
        return books.map((b) => ({ type: 'book' as const, value: b }));
      case 'solved':
        return papers
          .filter((p) => Boolean(p.solution_key))
          .map((p) => ({ type: 'paper' as const, value: p }));
      case 'all':
      default:
        return allMixed;
    }
  }, [activeTab, papers, books, allMixed]);

  const solvedCount = useMemo(
    () => papers.filter((p) => Boolean(p.solution_key)).length,
    [papers]
  );

  const ITEMS_PER_PAGE = 2;
  const totalPages = Math.max(1, Math.ceil(filteredItems.length / ITEMS_PER_PAGE));

  // Reset page when tab changes
  useEffect(() => {
    setCurrentPage(0);
  }, [activeTab]);

  // Auto-advance carousel smoothly, pause on hover
  useEffect(() => {
    if (totalPages <= 1 || isHovered) return;
    const interval = setInterval(() => {
      setCurrentPage((prev) => (prev + 1) % totalPages);
    }, 5500);
    return () => clearInterval(interval);
  }, [totalPages, isHovered]);

  const displayedItems = filteredItems.slice(
    currentPage * ITEMS_PER_PAGE,
    (currentPage + 1) * ITEMS_PER_PAGE
  );

  const handlePrev = () => {
    setCurrentPage((prev) => (prev === 0 ? totalPages - 1 : prev - 1));
  };

  const handleNext = () => {
    setCurrentPage((prev) => (prev + 1) % totalPages);
  };

  return (
    <div
      className="theme-highlight-shell rounded-[2rem] p-4 sm:p-5 backdrop-blur-xl transition-all duration-300 shadow-xl"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* 1. Header with Title, Live Activity Badge & Page Controls */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 mb-3">
        <div>
          <div className="flex items-center gap-2">
            <p className="text-xs font-bold uppercase tracking-[0.22em] text-primary flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5" />
              Highlighted resources
            </p>
          </div>
          <h2 className="mt-0.5 text-base sm:text-lg font-bold text-foreground">
            What students are opening most
          </h2>
        </div>

        <div className="flex items-center gap-2">
          <Badge className="theme-highlight-stat shrink-0 hover:bg-transparent gap-1.5 px-2.5 py-1">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>Live picks</span>
          </Badge>

          {/* Carousel Arrows */}
          {totalPages > 1 && (
            <div className="flex items-center gap-1 bg-card/80 dark:bg-card/60 p-0.5 rounded-full border border-border/60 shadow-xs">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={handlePrev}
                className="h-6 w-6 rounded-full hover:bg-primary/10 text-foreground hover:text-primary"
                title="Previous page"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </Button>
              <span className="text-[10px] font-semibold px-1 text-muted-foreground min-w-[28px] text-center">
                {currentPage + 1}/{totalPages}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={handleNext}
                className="h-6 w-6 rounded-full hover:bg-primary/10 text-foreground hover:text-primary"
                title="Next page"
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* 2. Sleek Filter Pills Bar */}
      <div className="flex items-center gap-1.5 pb-2.5 mb-3 border-b border-border/40 overflow-x-auto">
        <button
          type="button"
          onClick={() => setActiveTab('all')}
          className={`text-xs px-2.5 py-1 rounded-full font-medium transition-all flex items-center gap-1 shrink-0 ${
            activeTab === 'all'
              ? 'bg-primary text-primary-foreground font-semibold shadow-xs'
              : 'bg-card/70 dark:bg-card/40 hover:bg-card text-muted-foreground hover:text-foreground border border-border/60'
          }`}
        >
          <Flame className="h-3 w-3" />
          <span>All ({allMixed.length})</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('papers')}
          className={`text-xs px-2.5 py-1 rounded-full font-medium transition-all flex items-center gap-1 shrink-0 ${
            activeTab === 'papers'
              ? 'bg-primary text-primary-foreground font-semibold shadow-xs'
              : 'bg-card/70 dark:bg-card/40 hover:bg-card text-muted-foreground hover:text-foreground border border-border/60'
          }`}
        >
          <FileText className="h-3 w-3" />
          <span>Papers ({papers.length})</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('books')}
          className={`text-xs px-2.5 py-1 rounded-full font-medium transition-all flex items-center gap-1 shrink-0 ${
            activeTab === 'books'
              ? 'bg-primary text-primary-foreground font-semibold shadow-xs'
              : 'bg-card/70 dark:bg-card/40 hover:bg-card text-muted-foreground hover:text-foreground border border-border/60'
          }`}
        >
          <BookOpen className="h-3 w-3" />
          <span>Books ({books.length})</span>
        </button>

        {solvedCount > 0 && (
          <button
            type="button"
            onClick={() => setActiveTab('solved')}
            className={`text-xs px-2.5 py-1 rounded-full font-medium transition-all flex items-center gap-1 shrink-0 ${
              activeTab === 'solved'
                ? 'bg-amber-600 text-white font-semibold shadow-xs'
                : 'bg-card/70 dark:bg-card/40 hover:bg-card text-muted-foreground hover:text-foreground border border-border/60'
            }`}
          >
            <Star className="h-3 w-3 fill-amber-500 text-amber-500" />
            <span>Solved ({solvedCount})</span>
          </button>
        )}
      </div>

      {/* 3. Grid of High-Contrast Elevated Cards matching reference mockup */}
      {loading && !allMixed.length ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 min-h-[14rem]">
          {[1, 2].map((i) => (
            <div key={i} className="theme-highlight-card rounded-2xl p-4 animate-pulse space-y-2.5">
              <div className="h-24 bg-muted/70 rounded-xl" />
              <div className="h-4 bg-muted/60 rounded-full w-3/4" />
              <div className="h-3 bg-muted/40 rounded-full w-1/2" />
            </div>
          ))}
        </div>
      ) : filteredItems.length === 1 ? (
        <div className="min-h-[12rem] flex items-center justify-center">
          <div className="w-full max-w-sm">
            <HighlightResourceTile item={filteredItems[0]} uploaderProfiles={uploaderProfiles} />
          </div>
        </div>
      ) : displayedItems.length > 0 ? (
        <div className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {displayedItems.map((item, idx) => (
              <HighlightResourceTile
                key={`${item.type}-${item.value.id}-${currentPage}-${idx}`}
                item={item}
                uploaderProfiles={uploaderProfiles}
              />
            ))}
          </div>

          {/* Dots Indicator */}
          {totalPages > 1 && (
            <div className="flex justify-center items-center gap-1.5 pt-1">
              {Array.from({ length: totalPages }).map((_, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setCurrentPage(i)}
                  className={`h-1.5 rounded-full transition-all duration-300 ${
                    i === currentPage
                      ? 'w-6 bg-primary'
                      : 'w-1.5 bg-muted-foreground/30 hover:bg-muted-foreground/60'
                  }`}
                  aria-label={`Go to page ${i + 1}`}
                />
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="theme-highlight-card rounded-2xl p-6 text-center space-y-3 min-h-[12rem] flex flex-col items-center justify-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <BookOpen className="h-5 w-5" />
          </div>
          <div className="space-y-1 max-w-xs">
            <p className="text-sm font-bold text-foreground">No items in this category</p>
            <p className="text-xs text-muted-foreground">
              {activeTab === 'solved'
                ? 'No solved past papers yet. Submit verified solutions to appear here!'
                : 'Upload past papers and books to feature them in the spotlight.'}
            </p>
          </div>
          <Button size="sm" onClick={() => navigate('/upload')} className="theme-accent-bg text-xs">
            <Upload className="h-3.5 w-3.5 mr-1.5" />
            Upload Resources
          </Button>
        </div>
      )}

      {/* 4. Library Summary Footer */}
      {allMixed.length > 0 && (
        <div className="mt-3 pt-2.5 border-t border-border/40 flex items-center justify-between text-xs">
          <span className="theme-highlight-muted flex items-center gap-1.5 font-medium">
            <span>
              {papers.length} {papers.length === 1 ? 'Paper' : 'Papers'}
              {books.length ? ` · ${books.length} ${books.length === 1 ? 'Book' : 'Books'}` : ''} in Library
            </span>
          </span>
          <Link to="/resources" className="font-semibold text-primary hover:underline flex items-center gap-1 group">
            <span>Browse All</span>
            <ArrowRight className="h-3.5 w-3.5 group-hover:translate-x-0.5 transition-transform" />
          </Link>
        </div>
      )}
    </div>
  );
}

function BookPickCard({ book, uploaderProfiles }: { book: Book; uploaderProfiles?: Record<string, { profile?: any; imageUrl?: string | null }>; }) {
  const uploaderName = uploaderProfiles?.[book.uploaded_by]?.profile?.display_name || book.uploader_name || (book.uploaded_by ? `Contributor ${book.uploaded_by}` : 'Academic Contributor');
  const uploaderAvatar = uploaderProfiles?.[book.uploaded_by]?.imageUrl ?? (book.uploader_profile_picture_key || undefined);

  return (
    <Link to={`/book/${book.id}`} className="block group h-full focus:outline-none">
      <Card className="theme-panel h-full overflow-hidden rounded-2xl border border-border/70 hover:border-primary/50 transition-all duration-300 hover:-translate-y-1 hover:shadow-lg flex flex-col justify-between">
        <div className="p-3 pb-0">
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
        <CardContent className="p-3 pt-2.5 flex flex-col justify-between flex-1 gap-2">
          <div>
            <div className="flex items-center justify-between gap-1.5 mb-1.5">
              <span className="inline-flex items-center rounded-full border border-purple-500/50 bg-purple-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-purple-700 dark:text-purple-400">
                📚 Book
              </span>

              <span className="inline-flex items-center gap-1 rounded-full bg-amber-100/90 dark:bg-amber-950/60 px-2.5 py-0.5 text-[11px] font-semibold text-amber-800 dark:text-amber-300">
                <Users className="h-3 w-3" />
                Community
              </span>
            </div>

            <h3 className="line-clamp-1 text-sm sm:text-base font-bold text-foreground group-hover:text-primary transition-colors leading-snug" title={book.title}>
              {book.title}
            </h3>

            <div className="mt-1 space-y-0.5 text-xs text-muted-foreground">
              <p className="flex items-center gap-1.5 font-medium text-foreground/85 truncate">
                <BookOpen className="h-3.5 w-3.5 text-amber-600 dark:text-amber-500 shrink-0" />
                <span className="truncate">{book.authors?.join(', ') || 'Author not specified'}</span>
              </p>
              <p className="flex items-center gap-1.5 truncate text-muted-foreground">
                <Clock className="h-3.5 w-3.5 text-muted-foreground/70 shrink-0" />
                <span className="truncate">{book.courses?.map((c) => c.code || c.name).join(' · ') || book.category || 'Reference book'}</span>
              </p>
            </div>
          </div>

          <div className="pt-2 border-t border-border/50 flex items-center justify-between gap-2 text-xs">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <div className="h-6 w-6 overflow-hidden rounded-full shrink-0 border border-border/40">
                <AvatarFallback
                  name={uploaderName}
                  imageUrl={uploaderAvatar}
                  imageAlt={`${uploaderName} avatar`}
                />
              </div>
              <span className="font-semibold text-foreground/90 truncate text-xs">{uploaderName}</span>
            </div>
            <div className="flex items-center gap-1 text-muted-foreground text-xs shrink-0">
              <Download className="h-3.5 w-3.5 text-muted-foreground/70" />
              <span>{book.download_count || 0}</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
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
  const hasPersonalizedContent = Boolean(
    personalized && (personalized.recommended.length > 0 || personalized.recently_viewed.length > 0)
  );

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

            <div className="lg:justify-self-end w-full max-w-xl lg:max-w-2xl">
              <HighlightedResourcesShowcase
                papers={papers}
                books={books}
                loading={loading}
                uploaderProfiles={uploaderProfiles}
              />
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
