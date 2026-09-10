import { useState, useEffect, useMemo } from 'react';
import { Link, useSearchParams, useNavigate } from 'react-router-dom';
import { fetchAllPapers, getCachedPaperListSnapshot, Paper, resolvePublicUserProfiles } from '../lib/client';
import { fetchBooks, type Book } from '../lib/books';
import AvatarFallback from '../components/AvatarFallback';
import OfflineDataBanner from '../components/OfflineDataBanner';
import ExpandableContentSection from '../components/ExpandableContentSection';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Search,
  Download,
  CheckCircle,
  Users,
  BookOpen,
  Clock,
  Star,
  Filter,
  X,
} from 'lucide-react';

const PAPER_TYPES = ['Exam', 'CAT', 'Assignment', 'GroupWork'];
const BOOK_LANGUAGES = ['en', 'fr', 'rw', 'sw', 'ar', 'zh', 'es', 'pt', 'de', 'it', 'ja', 'ko', 'hi', 'ru', 'other'];
const YEARS = [2026, 2025, 2024, 2023, 2022, 2021, 2020];

function VerificationBadge({ status }: { status: string }) {
  if (status === 'verified') {
    return (
      <Badge className="theme-status-badge--verified hover:bg-inherit">
        <CheckCircle className="mr-1 h-3 w-3" />
        Verified
      </Badge>
    );
  }
  if (status === 'community') {
    return (
      <Badge className="theme-status-badge--community hover:bg-inherit">
        <Users className="mr-1 h-3 w-3" />
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

export default function SearchResults() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const [papers, setPapers] = useState<Paper[]>([]);
  const [books, setBooks] = useState<Book[]>([]);
  const [resourceType, setResourceType] = useState<'all' | 'paper' | 'book'>((searchParams.get('resource') as 'all' | 'paper' | 'book') || 'all');
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState(searchParams.get('q') || '');
  const [college, setCollege] = useState(searchParams.get('college') || '');
  const [department, setDepartment] = useState(searchParams.get('department') || '');
  const [course, setCourse] = useState(searchParams.get('course') || '');
  const [module, setModule] = useState(searchParams.get('module') || '');
  const [paperType, setPaperType] = useState(searchParams.get('type') || '');
  const [year, setYear] = useState(searchParams.get('year') || '');
  const [uploader, setUploader] = useState(searchParams.get('uploader') || '');
  const [language, setLanguage] = useState(searchParams.get('language') || '');
  const [sortBy, setSortBy] = useState(searchParams.get('sort') || '-download_count');
  const [showFilters, setShowFilters] = useState(false);
  const [showOfflineBanner, setShowOfflineBanner] = useState(false);
  const [uploaderProfiles, setUploaderProfiles] = useState<Record<string, { profile?: any; imageUrl?: string | null }>>({});

  useEffect(() => {
    const cached = getCachedPaperListSnapshot();
    if (cached) {
      setShowOfflineBanner(cached.data_source === 'cache');
      setPapers(cached.items.filter((paper) => !paper.is_hidden));
      setLoading(false);
    }
    void loadPapers();
    void fetchBooks().then((data) => setBooks(data.items)).catch(() => setBooks([]));
  }, []);

  useEffect(() => {
    setSearchQuery(searchParams.get('q') || '');
    setCollege(searchParams.get('college') || '');
    setDepartment(searchParams.get('department') || '');
    setCourse(searchParams.get('course') || '');
    setModule(searchParams.get('module') || '');
    setPaperType(searchParams.get('type') || '');
    setYear(searchParams.get('year') || '');
    setUploader(searchParams.get('uploader') || '');
    setLanguage(searchParams.get('language') || '');
    setSortBy(searchParams.get('sort') || '-download_count');
    const resource = searchParams.get('resource');
    setResourceType(resource === 'paper' || resource === 'book' ? resource : 'all');
  }, [searchParams]);

  // uploaderProfiles effect moved below filteredPapers declaration to avoid
  // referencing the memoized value before initialization.

  useEffect(() => {
    const params = new URLSearchParams();
    if (searchQuery) params.set('q', searchQuery);
    if (college) params.set('college', college);
    if (department) params.set('department', department);
    if (course) params.set('course', course);
    if (module) params.set('module', module);
    if (paperType) params.set('type', paperType);
    if (year) params.set('year', year);
    if (uploader) params.set('uploader', uploader);
    if (language) params.set('language', language);
    if (sortBy) params.set('sort', sortBy);
    if (resourceType !== 'all') params.set('resource', resourceType);
    setSearchParams(params);
  }, [searchQuery, college, department, course, module, paperType, year, uploader, language, sortBy, resourceType, setSearchParams]);

  const loadPapers = async () => {
    try {
      setLoading(true);
      const data = await fetchAllPapers({ sort: '-created_at', limit: 200 });
      setShowOfflineBanner(data.data_source === 'cache');
      setPapers(data.items.filter((paper) => !paper.is_hidden));
    } catch (err) {
      console.error('Failed to load papers:', err);
    } finally {
      setLoading(false);
    }
  };

  const departments = useMemo(() => {
    if (!college) return [];
    return Array.from(new Set(papers.filter((paper) => paper.college === college).map((paper) => paper.department))).sort();
  }, [papers, college]);
  const colleges = useMemo(() => Array.from(new Set(papers.map((paper) => paper.college).filter(Boolean))).sort(), [papers]);

  const courses = useMemo(() => {
    const paperCourses = papers
      .filter((paper) => (!college || paper.college === college) && (!department || paper.department === department))
      .map((paper) => [paper.course_code, `${paper.course_code} - ${paper.course_name}`] as const);
    const bookCourses = books.map((book) => book.courses || []).flat().map((item) => [item.code || String(item.id), `${item.code || 'Course'} - ${item.name}`] as const);
    return Array.from(new Map([...paperCourses, ...bookCourses]).entries());
  }, [papers, books, college, department]);

  const uploaderDisplayMap = useMemo(() => {
    const map = new Map<string, string>();
    papers.forEach((paper) => {
      map.set(paper.user_id, paper.uploader_display_name || 'Unknown uploader');
    });
    books.forEach((book) => map.set(book.uploaded_by, book.uploader_name || 'Unknown uploader'));
    return map;
  }, [papers, books]);

  const uploaders = useMemo(() => Array.from(new Set([...papers.map((paper) => paper.user_id), ...books.map((book) => book.uploaded_by)])).sort(), [papers, books]);
  const modules = useMemo(() => Array.from(new Map(books.flatMap((book) => book.modules || []).map((item) => [String(item.id), item.name])).entries()), [books]);

  const filteredPapers = useMemo(() => {
    let result = [...papers];

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (paper) =>
          paper.title.toLowerCase().includes(q) ||
          paper.course_code.toLowerCase().includes(q) ||
          paper.course_name.toLowerCase().includes(q) ||
          (paper.lecturer && paper.lecturer.toLowerCase().includes(q)) ||
          (paper.description && paper.description.toLowerCase().includes(q)) ||
          paper.user_id.toLowerCase().includes(q) ||
          (paper.uploader_display_name && paper.uploader_display_name.toLowerCase().includes(q))
      );
    }

    if (college) result = result.filter((paper) => paper.college === college);
    if (department) result = result.filter((paper) => paper.department === department);
    if (course) result = result.filter((paper) => paper.course_code === course);
    if (paperType) result = result.filter((paper) => paper.paper_type === paperType);
    if (year) result = result.filter((paper) => paper.year === parseInt(year, 10));
    if (uploader) result = result.filter((paper) => paper.user_id === uploader);

    if (sortBy === '-download_count') {
      result.sort((a, b) => (b.download_count || 0) - (a.download_count || 0));
    } else if (sortBy === '-created_at') {
      result.sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime());
    } else if (sortBy === 'title') {
      result.sort((a, b) => a.title.localeCompare(b.title));
    } else if (sortBy === '-year') {
      result.sort((a, b) => b.year - a.year);
    }

    return result;
  }, [papers, searchQuery, college, department, course, paperType, year, uploader, sortBy]);

  const filteredBooks = useMemo(() => books.filter((book) => {
    const q = searchQuery.trim().toLowerCase();
    if (q && ![book.title, book.description, book.isbn, book.publisher, book.authors.join(' '), book.uploader_name, book.course_ids.join(' '), ...(book.courses || []).flatMap((item) => [item.code, item.name]), ...(book.modules || []).map((item) => item.name)].filter(Boolean).some((value) => String(value).toLowerCase().includes(q))) return false;
    if (year && book.publication_year !== Number(year)) return false;
    if (language && book.language !== language) return false;
    if (course && !(book.courses || []).some((item) => item.code === course || String(item.id) === course)) return false;
    if (module && !(book.modules || []).some((item) => String(item.id) === module)) return false;
    if (uploader && book.uploaded_by !== uploader) return false;
    return true;
  }), [books, searchQuery, year, language, course, module, uploader]);
  const sortedBooks = useMemo(() => [...filteredBooks].sort((a, b) => {
    if (sortBy === 'title') return a.title.localeCompare(b.title);
    if (sortBy === '-year') return (b.publication_year || 0) - (a.publication_year || 0);
    if (sortBy === '-download_count') return (b.download_count || 0) - (a.download_count || 0);
    return new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime();
  }), [filteredBooks, sortBy]);
  const visiblePaperResults = resourceType !== 'book' ? filteredPapers : [];
  const visibleBookResults = resourceType !== 'paper' ? sortedBooks : [];

  // resolve uploader public profiles for visible results
  useEffect(() => {
    const ids = Array.from(new Set(filteredPapers.map((p) => p.user_id)));
    if (ids.length === 0) return;
    let cancelled = false;
    (async () => {
      try {
        const resolved = await resolvePublicUserProfiles(ids);
        if (cancelled) return;
        const next: Record<string, { profile?: any; imageUrl?: string | null }> = {};
        for (const id of ids) {
          const r = resolved[id];
          next[id] = { profile: r?.profile || undefined, imageUrl: r?.imageUrl ?? null };
        }
        setUploaderProfiles(next);
      } catch (e) {
        // ignore
      }
    })();
    return () => { cancelled = true; };
  }, [filteredPapers]);

  const clearFilters = () => {
    setSearchQuery('');
    setCollege('');
    setDepartment('');
    setCourse('');
    setModule('');
    setPaperType('');
    setYear('');
    setUploader('');
    setLanguage('');
    setSortBy('-download_count');
    setSearchParams({});
  };

  const activeChips = [
    college,
    department,
    course,
    module ? modules.find(([id]) => id === module)?.[1] || module : '',
    year,
    paperType,
    uploader ? uploaderDisplayMap.get(uploader) || uploader : '',
    language,
  ].filter(Boolean);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {showOfflineBanner && (
        <OfflineDataBanner message="These search results are coming from cached paper data while the live service is unavailable." />
      )}
      <div className="theme-overlay-card mb-8 rounded-2xl border p-4 backdrop-blur">
        
        <div className="mb-4 flex flex-wrap gap-2"><Button size="sm" variant={resourceType === 'all' ? 'default' : 'outline'} onClick={() => setResourceType('all')}>All Resources</Button><Button size="sm" variant={resourceType === 'paper' ? 'default' : 'outline'} onClick={() => setResourceType('paper')}>📄 Papers</Button><Button size="sm" variant={resourceType === 'book' ? 'default' : 'outline'} onClick={() => setResourceType('book')}>📚 Books</Button></div>
        <form
          onSubmit={(event) => event.preventDefault()}
          className="flex flex-col gap-2 md:flex-row"
        >
          <div className="relative flex-1">
            <Search className="theme-muted absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by course code, course name, title, author, module, lecturer, uploader, ISBN, or keyword..."
              className="h-11 pl-10"
            />
          </div>
          <Button
            type="button"
            variant="outline"
            className="relative h-11"
            onClick={() => setShowFilters((prev) => !prev)}
          >
            <Filter className="mr-2 h-4 w-4" />
            Filters
            {activeChips.length > 0 && (
              <span className="theme-accent-bg absolute -right-2 -top-2 flex h-5 w-5 items-center justify-center rounded-full text-xs">
                {activeChips.length}
              </span>
            )}
          </Button>
        </form>
      </div>

      {showFilters && (
        <Card className="theme-panel mb-6">
          <CardContent className="p-4">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="theme-title font-semibold">Filters</h3>
              <Button variant="ghost" size="sm" onClick={clearFilters} className="theme-ghost-brand-button">
                <X className="mr-1 h-4 w-4" />
                Clear All
              </Button>
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <label className="theme-muted mb-1 block text-sm font-medium">College</label>
                <Select value={college || 'all'} onValueChange={(value) => { setCollege(value === 'all' ? '' : value); setDepartment(''); setCourse(''); }}>
                  <SelectTrigger>
                    <SelectValue placeholder="All Colleges" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Colleges</SelectItem>
                    {colleges.map((item) => (
                      <SelectItem key={item} value={item}>{item.replace('College of ', '')}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="theme-muted mb-1 block text-sm font-medium">Department</label>
                <Select value={department || 'all'} onValueChange={(value) => { setDepartment(value === 'all' ? '' : value); setCourse(''); }}>
                  <SelectTrigger>
                    <SelectValue placeholder="All Departments" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Departments</SelectItem>
                    {departments.map((item) => (
                      <SelectItem key={item} value={item}>{item}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="theme-muted mb-1 block text-sm font-medium">Course</label>
                <Select value={course || 'all'} onValueChange={(value) => setCourse(value === 'all' ? '' : value)}>
                  <SelectTrigger>
                    <SelectValue placeholder="All Courses" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Courses</SelectItem>
                    {courses.map(([code, label]) => (
                      <SelectItem key={code} value={code}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="theme-muted mb-1 block text-sm font-medium">Module</label>
                <Select value={module || 'all'} onValueChange={(value) => setModule(value === 'all' ? '' : value)}>
                  <SelectTrigger><SelectValue placeholder="All Modules" /></SelectTrigger>
                  <SelectContent><SelectItem value="all">All Modules</SelectItem>{modules.map(([id, name]) => <SelectItem key={id} value={id}>{name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div>
                <label className="theme-muted mb-1 block text-sm font-medium">Paper Type</label>
                <Select value={paperType || 'all'} onValueChange={(value) => setPaperType(value === 'all' ? '' : value)}>
                  <SelectTrigger>
                    <SelectValue placeholder="All Types" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Types</SelectItem>
                    {PAPER_TYPES.map((item) => (
                      <SelectItem key={item} value={item}>{item}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="theme-muted mb-1 block text-sm font-medium">Year</label>
                <Select value={year || 'all'} onValueChange={(value) => setYear(value === 'all' ? '' : value)}>
                  <SelectTrigger>
                    <SelectValue placeholder="All Years" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Years</SelectItem>
                    {YEARS.map((item) => (
                      <SelectItem key={item} value={String(item)}>{item}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="theme-muted mb-1 block text-sm font-medium">Uploader</label>
                <Select value={uploader || 'all'} onValueChange={(value) => setUploader(value === 'all' ? '' : value)}>
                  <SelectTrigger>
                    <SelectValue placeholder="All Uploaders" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Uploaders</SelectItem>
                    {uploaders.map((item) => (
                      <SelectItem key={item} value={item}>
                        {uploaderDisplayMap.get(item) || item}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="theme-muted mb-1 block text-sm font-medium">Language</label>
                <Select value={language || 'all'} onValueChange={(value) => setLanguage(value === 'all' ? '' : value)}>
                  <SelectTrigger><SelectValue placeholder="All Languages" /></SelectTrigger>
                  <SelectContent><SelectItem value="all">All Languages</SelectItem>{BOOK_LANGUAGES.map((item) => <SelectItem key={item} value={item}>{item.toUpperCase()}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div>
                <label className="theme-muted mb-1 block text-sm font-medium">Sort By</label>
                <Select value={sortBy} onValueChange={setSortBy}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="-download_count">Most Downloaded</SelectItem>
                    <SelectItem value="-created_at">Most Recent</SelectItem>
                    <SelectItem value="title">Title A-Z</SelectItem>
                    <SelectItem value="-year">Newest Year</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            {activeChips.length > 0 && (
              <div className="mt-4">
                <label className="theme-muted mb-2 block text-sm font-medium">Filter chips</label>
                <div className="flex flex-wrap gap-2">
                  {activeChips.map((chip) => (
                    <Badge key={chip} variant="secondary">{chip}</Badge>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <div className="mb-4 flex items-center justify-between">
        <p className="theme-muted text-sm">
          {loading ? 'Loading...' : resourceType === 'all' ? `${visiblePaperResults.length + visibleBookResults.length} resources found` : resourceType === 'paper' ? `${visiblePaperResults.length} papers found` : `${visibleBookResults.length} books found`}
        </p>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((item) => (
            <Card key={item} className="theme-panel animate-pulse">
              <CardContent className="space-y-3 p-5">
                <div className="h-4 w-1/3 rounded bg-muted" />
                <div className="h-5 w-full rounded bg-muted" />
                <div className="h-4 w-2/3 rounded bg-muted" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : visiblePaperResults.length + visibleBookResults.length === 0 ? (
        <div className="py-16 text-center">
          <img
            src="/assets/illustrations/search-empty.svg"
            alt="No matching academic papers"
            className="mx-auto mb-6 h-48 w-48 rounded-lg opacity-70"
          />
          <h3 className="theme-title mb-2 text-xl font-semibold">No resources found</h3>
          <p className="theme-muted mb-4">Try adjusting your search or filters</p>
          <Button onClick={clearFilters} className="theme-accent-bg">
            Clear Filters
          </Button>
        </div>
      ) : (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {visiblePaperResults.map((paper) => (
              <Link key={paper.id} to={`/paper/${paper.id}`} className="block">
                <Card className="theme-panel group border transition-all duration-300 hover:-translate-y-1 hover:shadow-lg">
                  <CardContent className="p-5">
                    <div className="mb-3 flex items-start justify-between">
                      <Badge variant="outline" className="border-primary text-xs font-medium text-primary">
                        📄 PAPER · {paper.paper_type}
                      </Badge>
                      <VerificationBadge status={paper.verification_status} />
                    </div>
                    <h3 className="theme-title mb-2 line-clamp-2 font-semibold transition-colors group-hover:text-primary">
                      {paper.title}
                    </h3>
                    <div className="flex items-center gap-3 mt-2">
                      <div className="h-8 w-8 overflow-hidden rounded-full">
                        <AvatarFallback
                          name={uploaderProfiles[paper.user_id]?.profile?.display_name || paper.uploader_display_name || `Uploader ${paper.user_id}`}
                          imageUrl={uploaderProfiles[paper.user_id]?.imageUrl ?? undefined}
                          imageAlt={`${uploaderProfiles[paper.user_id]?.profile?.display_name || paper.uploader_display_name || 'Uploader'} avatar`}
                        />
                      </div>
                      <div className="text-xs theme-muted">
                        <div className="font-medium text-sm">{uploaderProfiles[paper.user_id]?.profile?.display_name || paper.uploader_display_name || `Uploader ${paper.user_id}`}</div>
                        <div>{paper.course_code} · {paper.year}</div>
                      </div>
                    </div>
                    <div className="theme-muted space-y-1 text-sm">
                      <p className="flex items-center gap-1">
                        <BookOpen className="h-3.5 w-3.5" />
                        {paper.course_code} - {paper.course_name}
                      </p>
                      <p className="flex items-center gap-1">
                        <Clock className="h-3.5 w-3.5" />
                        {paper.year} - {paper.department}
                      </p>
                      {paper.lecturer && <p className="theme-muted text-xs">By {paper.lecturer}</p>}
                      <p className="theme-muted text-xs">
                        Uploader {paper.uploader_display_name || paper.user_id}
                      </p>
                    </div>
                    <div className="mt-4 flex items-center justify-between border-t pt-3">
                      <span className="theme-muted flex items-center gap-1 text-xs">
                        <Download className="h-3.5 w-3.5" />
                        {paper.download_count || 0}
                      </span>
                      {paper.solution_key && (
                        <Badge className="theme-status-badge--solution text-xs hover:bg-inherit">
                          <Star className="mr-1 h-3 w-3" />
                          Solution
                        </Badge>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
            {visibleBookResults.map((book) => (
              <Link key={`book-${book.id}`} to={`/book/${book.id}`} className="block"><Card className="theme-panel group border transition-all duration-300 hover:-translate-y-1 hover:shadow-lg"><CardContent className="p-5"><div className="mb-3 flex items-start justify-between"><Badge variant="outline" className="border-primary text-xs font-medium text-primary">📚 BOOK</Badge>{book.cover_key && <BookOpen className="h-5 w-5 text-muted-foreground" />}</div><h3 className="theme-title mb-2 line-clamp-2 font-semibold transition-colors group-hover:text-primary">{book.title}</h3><div className="theme-muted space-y-1 text-sm"><p>{book.authors.join(', ') || 'Author not specified'}</p><p>{book.courses?.map((item) => item.code || item.name).join(' · ') || 'No related course'}</p><p>{book.modules?.map((module) => module.name).join(' · ')}</p><p>{book.language} {book.edition ? `· ${book.edition}` : ''}</p><p>Uploaded by {book.uploader_name || book.uploaded_by}</p></div><div className="mt-4 border-t pt-3 text-sm font-medium text-primary">Open Book</div></CardContent></Card></Link>
            ))}
          </div>
      )}

      <ExpandableContentSection
        className="mt-10"
        title="How to find the right University of Rwanda past papers faster"
        summary="Open this guide for search tips, revision advice, and extra context about how this page helps students find the most relevant UR exam papers."
        expandLabel="Open guide"
        collapseLabel="Hide guide"
      >
        <p className="theme-muted text-base leading-8">
          This page is built for students who already know that good revision starts with the right examples. Instead of scrolling through unorganized files, you can search by course code, filter by department, or narrow results to a specific paper type such as an exam, CAT, assignment, or group work. That helps you get from a broad query like computer science revision to a focused set of <strong>UR exam papers</strong> you can actually use.
        </p>
        <p className="theme-muted text-base leading-8">
          Strong search pages also matter for visibility in Google. When a page clearly explains the value of its content, search engines understand that it is not just a tool, but a useful library of <strong>University of Rwanda past papers</strong> and revision support. That is why this section explains the page purpose in plain language. Students visit to compare paper types, spot recurring assessment patterns, and identify the most relevant <strong>study materials Rwanda</strong> learners are already downloading and discussing.
        </p>
        <p className="theme-muted text-base leading-8">
          If you are exploring for the first time, begin with the college and course filters, then sort by most downloaded to see what has already helped other learners. If you already know the exact course code, use the keyword search first and then refine the list by year or uploader. The result is a cleaner, more indexable resource page that serves both search engines and real students preparing for University of Rwanda assessments.
        </p>
      </ExpandableContentSection>
    </div>
  );
}
