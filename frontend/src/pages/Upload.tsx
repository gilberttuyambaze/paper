import { buildStorageKey, normalizeIsbn, normalizeText as normalizeUserText, normalizeUnique } from '../lib/normalization';
import { useState, useEffect, useRef, type DragEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { createPaper, extractUploadPdfText, fetchAllPapers, fetchUserProfile, uploadFileObject, type Paper, type UserProfile } from '../lib/client';
import { authApi } from '../lib/auth';
import { useAuth } from '../contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Upload as UploadIcon, FileText, ArrowLeft, CheckCircle, Sparkles, LoaderCircle } from 'lucide-react';
import { toast } from '@/lib/messages';
import { normalizeApiError } from '@/lib/api-errors';
import AcademicContextFields, { type AcademicContextValue } from '@/components/AcademicContextFields';
import InlineFieldMessage from '@/components/InlineFieldMessage';
import { createBook, createCourse, createModule, fetchModules, searchCourses, type Book, type Course, type Module } from '@/lib/books';
import { useUploadAccess, type UploadResourceType } from '@/hooks/useUploadAccess';

const PAPER_TYPES = ['Exam', 'CAT', 'Assignment', 'GroupWork'];
const STUDY_YEARS = ['Year 1', 'Year 2', 'Year 3', 'Year 4', 'Year 5', 'Postgraduate'];
const SEMESTERS = ['Semester 1', 'Semester 2', 'Trimester 1', 'Trimester 2', 'Trimester 3', 'Annual'];

const YEARS = [2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018];
const CUSTOM_COURSE_OPTION = '__custom__';
const MAX_SUGGESTION_AUTO_RETRIES = 3;
const SUGGESTION_RETRY_DELAYS_MS = [300, 900, 1800];

function isPdfFile(file: File | null) {
  if (!file) return false;
  const normalizedName = file.name.toLowerCase();
  return file.type === 'application/pdf' || normalizedName.endsWith('.pdf');
}

type DetectedUploadHints = {
  title?: string;
  courseCode?: string;
  courseName?: string;
  college?: string;
  department?: string;
  year?: string;
  yearOfStudy?: string;
  semester?: string;
  paperType?: string;
  lecturer?: string;
  evidence: string[];
};

function detectYearOfStudy(corpus: string): string | undefined {
  const lower = corpus.toLowerCase();
  if (/\b(?:year\s*1|1st\s*year|first\s*year|level\s*1|l1|y1)\b/i.test(lower)) return 'Year 1';
  if (/\b(?:year\s*2|2nd\s*year|second\s*year|level\s*2|l2|y2)\b/i.test(lower)) return 'Year 2';
  if (/\b(?:year\s*3|3rd\s*year|third\s*year|level\s*3|l3|y3)\b/i.test(lower)) return 'Year 3';
  if (/\b(?:year\s*4|4th\s*year|fourth\s*year|level\s*4|l4|y4)\b/i.test(lower)) return 'Year 4';
  if (/\b(?:year\s*5|5th\s*year|fifth\s*year|level\s*5|l5|y5)\b/i.test(lower)) return 'Year 5';
  if (/\b(?:postgraduate|masters|master|phd|post-graduate)\b/i.test(lower)) return 'Postgraduate';
  return undefined;
}

function detectSemester(corpus: string): string | undefined {
  const lower = corpus.toLowerCase();
  if (/\b(?:semester\s*1|sem\s*1|s1|term\s*1)\b/i.test(lower)) return 'Semester 1';
  if (/\b(?:semester\s*2|sem\s*2|s2|term\s*2)\b/i.test(lower)) return 'Semester 2';
  if (/\b(?:trimester\s*1|tri\s*1|t1)\b/i.test(lower)) return 'Trimester 1';
  if (/\b(?:trimester\s*2|tri\s*2|t2)\b/i.test(lower)) return 'Trimester 2';
  if (/\b(?:trimester\s*3|tri\s*3|t3)\b/i.test(lower)) return 'Trimester 3';
  if (/\b(?:annual|full\s*year)\b/i.test(lower)) return 'Annual';
  return undefined;
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function normalizeExtractedText(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, ' ').replace(/\s+/g, ' ').trim();
}

function humanizeFileStem(filename: string) {
  return filename
    .replace(/\.pdf$/i, '')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

async function extractPdfPreviewText(file: File) {
  const chunkSize = 2_000_000;
  const fileSize = file.size;
  const ranges = [
    [0, Math.min(chunkSize, fileSize)],
    [Math.max(0, Math.floor(fileSize / 2) - Math.floor(chunkSize / 2)), Math.min(fileSize, Math.floor(fileSize / 2) + Math.floor(chunkSize / 2))],
    [Math.max(0, fileSize - chunkSize), fileSize],
  ] as const;

  const uniqueRanges = ranges.filter(
    ([start, end], index, allRanges) =>
      end > start && allRanges.findIndex(([otherStart, otherEnd]) => otherStart === start && otherEnd === end) === index
  );

  const buffers = await Promise.all(
    uniqueRanges.map(async ([start, end]) => {
      const buffer = await file.slice(start, end).arrayBuffer();
      return new TextDecoder('latin1').decode(new Uint8Array(buffer));
    })
  );

  return buffers
    .join(' ')
    .replace(/[^\x20-\x7E]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function detectPaperType(corpus: string) {
  const lower = corpus.toLowerCase();
  if (/\bgroup[\s_-]*work\b/.test(lower)) return 'GroupWork';
  if (/\bassignment\b/.test(lower)) return 'Assignment';
  if (/\bcat\b|\bcontinuous assessment\b/.test(lower)) return 'CAT';
  if (/\bexam\b|\bfinal\b|\bmidterm\b|\btest\b/.test(lower)) return 'Exam';
  return undefined;
}

function detectLecturer(corpus: string) {
  const patterns = [
    /(?:lecturer|instructor)\s*[:\-]\s*([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){0,3})/,
    /\b(?:Dr|Prof|Mr|Mrs|Ms)\.?\s+[A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){0,3}/,
  ];

  for (const pattern of patterns) {
    const match = corpus.match(pattern);
    if (match) {
      const value = (match[1] || match[0] || '').trim();
      if (value) return value;
    }
  }

  return undefined;
}

function detectYear(corpus: string) {
  const matches = corpus.match(/\b20(1[8-9]|2[0-6])\b/g) || [];
  if (!matches.length) return undefined;
  return matches.sort().reverse()[0];
}

function detectCourseCode(corpus: string) {
  const labelled = corpus.match(/(?:course\s*(?:code)?|module\s*(?:code)?)\s*[:#-]?\s*([A-Z]{2,6}\s?-?\s?\d{3,4})/i);
  const generic = corpus.match(/\b([A-Z]{2,6}\s?-?\s?\d{3,4})\b/);
  return (labelled?.[1] || generic?.[1] || '').replace(/[\s-]+/g, '').toUpperCase() || undefined;
}

function detectCourseName(corpus: string) {
  const match = corpus.match(/(?:course|module)\s*(?:title|name)?\s*[:\-]\s*([A-Z][A-Za-z0-9,&/()' -]{4,90})/i);
  return match?.[1]?.trim().replace(/\s{2,}/g, ' ') || undefined;
}

function buildDetectedHints(file: File, previewText: string, courseOptions: Paper[]): DetectedUploadHints | null {
  const filenameText = humanizeFileStem(file.name);
  const combinedText = `${filenameText} ${previewText}`;
  const normalizedCombined = normalizeExtractedText(combinedText);
  const evidence: string[] = [];
  const hints: DetectedUploadHints = { evidence };

  const courseByCode = [...courseOptions]
    .sort((left, right) => right.course_code.length - left.course_code.length)
    .find((paper) => new RegExp(`\\b${escapeRegExp(paper.course_code)}\\b`, 'i').test(combinedText));

  const courseByName =
    courseByCode ||
    courseOptions.find((paper) => {
      const normalizedCourseName = normalizeExtractedText(paper.course_name || '');
      return normalizedCourseName.length >= 6 && normalizedCombined.includes(normalizedCourseName);
    });

  const matchedCourse = courseByCode || courseByName;
  if (matchedCourse) {
    hints.courseCode = matchedCourse.course_code.toUpperCase();
    hints.courseName = matchedCourse.course_name;
    hints.college = matchedCourse.college;
    hints.department = matchedCourse.department;
    if (matchedCourse.paper_type) hints.paperType = matchedCourse.paper_type;
    if (matchedCourse.lecturer) hints.lecturer = matchedCourse.lecturer;
    evidence.push(`Matched existing course ${matchedCourse.course_code.toUpperCase()} from the uploaded PDF.`);
  } else {
    const detectedCourseCode = detectCourseCode(combinedText);
    const detectedCourseName = detectCourseName(previewText);
    if (detectedCourseCode) {
      hints.courseCode = detectedCourseCode;
      evidence.push(`Detected course code ${detectedCourseCode} from the PDF.`);
    }
    if (detectedCourseName) {
      hints.courseName = detectedCourseName;
      evidence.push(`Detected course name ${detectedCourseName}.`);
    }
  }

  const year = detectYear(combinedText);
  if (year) {
    hints.year = year;
    evidence.push(`Detected year ${year}.`);
  }

  const detectedPaperType = detectPaperType(combinedText);
  if (detectedPaperType) {
    hints.paperType = detectedPaperType;
    evidence.push(`Detected paper type ${detectedPaperType}.`);
  }

  const detectedYearOfStudy = detectYearOfStudy(combinedText);
  if (detectedYearOfStudy) {
    hints.yearOfStudy = detectedYearOfStudy;
    evidence.push(`Detected study year ${detectedYearOfStudy}.`);
  }

  const detectedSem = detectSemester(combinedText);
  if (detectedSem) {
    hints.semester = detectedSem;
    evidence.push(`Detected semester ${detectedSem}.`);
  }

  const lecturer = detectLecturer(previewText);
  if (lecturer) {
    hints.lecturer = lecturer;
    evidence.push(`Detected lecturer name ${lecturer}.`);
  }

  if (matchedCourse?.course_name) {
    hints.title = `${matchedCourse.course_name} - ${hints.paperType || 'Paper'}${hints.year ? ` ${hints.year}` : ''}`;
  } else if (hints.courseName) {
    hints.title = `${hints.courseName} - ${hints.paperType || 'Paper'}${hints.year ? ` ${hints.year}` : ''}`;
  } else if (filenameText) {
    hints.title = filenameText;
    evidence.push('Built a draft title from the PDF filename.');
  }

  return evidence.length ? hints : null;
}

export default function UploadPage() {
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const { canAccessUploadArea, allowedResourceTypes, loading: siteAccessLoading, error: siteAccessError } = useUploadAccess();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [uploadKind, setUploadKind] = useState<'paper' | 'book'>('paper');
  const [submitting, setSubmitting] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStage, setUploadStage] = useState<'paper' | 'solution' | 'publishing' | null>(null);
  const [success, setSuccess] = useState(false);
  const [uploadedPaper, setUploadedPaper] = useState<Paper | null>(null);
  const [uploadedBook, setUploadedBook] = useState<Book | null>(null);
  const [paperCatalog, setPaperCatalog] = useState<Paper[]>([]);
  const [selectedCourseOption, setSelectedCourseOption] = useState(CUSTOM_COURSE_OPTION);
  const [analyzingPaperFile, setAnalyzingPaperFile] = useState(false);
  const [detectedHints, setDetectedHints] = useState<DetectedUploadHints | null>(null);
  const [suggestionFeedback, setSuggestionFeedback] = useState<{
    tone: 'info' | 'success' | 'warning';
    message: string;
    canRetry?: boolean;
    retryLabel?: string;
  } | null>(null);
  const lastAnalyzedPaperKeyRef = useRef<string | null>(null);

  const [title, setTitle] = useState('');
  const [courseCode, setCourseCode] = useState('');
  const [courseName, setCourseName] = useState('');
  const [college, setCollege] = useState('');
  const [department, setDepartment] = useState('');
  const [academic, setAcademic] = useState<AcademicContextValue>({ institution_id: 'ur', campus_id: '', college_id: '', school_id: '', programme_id: '' });
  const [programmeNameOther, setProgrammeNameOther] = useState('');
  const [year, setYear] = useState('');
  const [yearOfStudy, setYearOfStudy] = useState('');
  const [semester, setSemester] = useState('');
  const [paperType, setPaperType] = useState('');
  const [lecturer, setLecturer] = useState('');
  const [description, setDescription] = useState('');
  const [paperFile, setPaperFile] = useState<File | null>(null);
  const [solutionFile, setSolutionFile] = useState<File | null>(null);
  const [paperDragActive, setPaperDragActive] = useState(false);
  const [solutionDragActive, setSolutionDragActive] = useState(false);
  const [bookTitle, setBookTitle] = useState('');
  const [bookDescription, setBookDescription] = useState('');
  const [bookIsbn, setBookIsbn] = useState('');
  const [bookEdition, setBookEdition] = useState('');
  const [bookYear, setBookYear] = useState('');
  const [bookYearOfStudy, setBookYearOfStudy] = useState('');
  const [bookSemester, setBookSemester] = useState('');
  const [bookLanguage, setBookLanguage] = useState('');
  const [bookPublisher, setBookPublisher] = useState('');
  const [bookCategory, setBookCategory] = useState('');
  const [bookSubject, setBookSubject] = useState('');
  const [bookAuthors, setBookAuthors] = useState<Array<{ name: string }>>([]);
  const [authorInput, setAuthorInput] = useState('');
  const [bookCourses, setBookCourses] = useState<Course[]>([]);
  const [courseQuery, setCourseQuery] = useState('');
  const [courseOptions, setCourseOptions] = useState<Course[]>([]);
  const [newCourseCode, setNewCourseCode] = useState('');
  const [newCourseDescription, setNewCourseDescription] = useState('');
  const [bookModules, setBookModules] = useState<Module[]>([]);
  const [moduleOptions, setModuleOptions] = useState<Module[]>([]);
  const [moduleQuery, setModuleQuery] = useState('');
  const [newModuleCode, setNewModuleCode] = useState('');
  const [newModuleDescription, setNewModuleDescription] = useState('');
  const [bookFile, setBookFile] = useState<File | null>(null);
  const [bookCover, setBookCover] = useState<File | null>(null);
  const [bookFileDragActive, setBookFileDragActive] = useState(false);
  const [bookCoverDragActive, setBookCoverDragActive] = useState(false);
  const enabledUploadKinds = allowedResourceTypes as UploadResourceType[];
  const selectedUploadKind = uploadKind as UploadResourceType;

  useEffect(() => {
    if (siteAccessLoading || enabledUploadKinds.length === 0) return;
    setUploadKind((current) => enabledUploadKinds.includes(current) ? current : enabledUploadKinds[0]);
  }, [siteAccessLoading, enabledUploadKinds.join(',')]);

  const handleDragOver = (
    event: DragEvent<HTMLDivElement>,
    setActive: React.Dispatch<React.SetStateAction<boolean>>
  ) => {
    event.preventDefault();
    event.stopPropagation();
    setActive(true);
  };

  const handleDragLeave = (
    event: DragEvent<HTMLDivElement>,
    setActive: React.Dispatch<React.SetStateAction<boolean>>
  ) => {
    event.preventDefault();
    event.stopPropagation();
    setActive(false);
  };

  const handleDropFile = (
    event: DragEvent<HTMLDivElement>,
    setFile: React.Dispatch<React.SetStateAction<File | null>>,
    setActive: React.Dispatch<React.SetStateAction<boolean>>,
    label: string,
    onAccepted?: (file: File) => void
  ) => {
    event.preventDefault();
    event.stopPropagation();
    setActive(false);
    const file = event.dataTransfer.files?.[0];
    if (file) {
      if (!isPdfFile(file)) {
        toast.error(`${label} must be a PDF file.`);
        return;
      }
      setFile(file);
      onAccepted?.(file);
    }
  };

  useEffect(() => {
    if (!user) return;
    void loadProfileAndSuggestions();
  }, [user]);

  const loadProfileAndSuggestions = async () => {
    try {
      const [profileData, paperData] = await Promise.all([
        fetchUserProfile(),
        fetchAllPapers({ sort: '-created_at', limit: 200 }),
      ]);
      setProfile(profileData);
      if (profileData?.campus_id) setAcademic({ institution_id: profileData.institution_id || 'ur', campus_id: profileData.campus_id || '', college_id: profileData.college_id || '', school_id: profileData.school_id || '', programme_id: profileData.programme_id || '' });
      if (profileData?.college_name) setCollege(profileData.college_name);
      if (profileData?.department_name) setDepartment(profileData.department_name);
      setPaperCatalog(paperData.items);
    } catch (error) {
      console.error('Failed to load upload helpers:', error);
    }
  };

  const inferVerificationStatus = () => {
    if (!profile) return 'unverified';
    if (user.permissions?.includes('uploads.paper') || user.permissions?.includes('uploads.book')) {
      return 'verified';
    }
    if (profile.role === 'verified_contributor' || (profile.trust_score || 0) >= 50) {
      return 'community';
    }
    return 'unverified';
  };

  const knownCourseOptions = Array.from(
    new Map(
      paperCatalog
        .filter((paper) => paper.course_code && paper.course_name)
        .map((paper) => [paper.course_code.toUpperCase(), paper])
    ).values()
  ).sort((left, right) => left.course_code.localeCompare(right.course_code));

  useEffect(() => {
    if (!paperFile || analyzingPaperFile) return;
    const analysisKey = `${paperFile.name}:${paperFile.size}:${paperFile.lastModified}`;
    if (lastAnalyzedPaperKeyRef.current === analysisKey) return;
    lastAnalyzedPaperKeyRef.current = analysisKey;
    void analyzePaperFile(paperFile);
  }, [paperFile, analyzingPaperFile]);

  const matchingSuggestions = paperCatalog.filter(
    (paper) =>
      !courseCode ||
      paper.course_code.toLowerCase().includes(courseCode.toLowerCase()) ||
      paper.course_name.toLowerCase().includes(courseCode.toLowerCase())
  ).slice(0, 8);

  const applySuggestion = (paper: Paper) => {
    setSelectedCourseOption(paper.course_code.toUpperCase());
    setCourseCode(paper.course_code);
    setCourseName(paper.course_name);
    setCollege(paper.college);
    setDepartment(paper.department);
    setPaperType(paper.paper_type);
    if (paper.year_of_study) setYearOfStudy(paper.year_of_study);
    if (paper.semester) setSemester(paper.semester);
    setLecturer(paper.lecturer || '');
  };

  const applyDetectedHints = (hints: DetectedUploadHints, overwrite = false) => {
    if (hints.courseCode) {
      const matchedCourse = knownCourseOptions.find((paper) => paper.course_code.toUpperCase() === hints.courseCode);
      setSelectedCourseOption(matchedCourse ? hints.courseCode : CUSTOM_COURSE_OPTION);
      setCourseCode((current) => (overwrite || !current ? hints.courseCode || current : current));
      if (matchedCourse) {
        setCourseName((current) => (overwrite || !current ? matchedCourse.course_name : current));
        setCollege((current) => (overwrite || !current ? matchedCourse.college : current));
        setDepartment((current) => (overwrite || !current ? matchedCourse.department : current));
      }
    }

    if (hints.title) {
      setTitle((current) => (overwrite || !current ? hints.title || current : current));
    }
    if (hints.courseName) {
      setCourseName((current) => (overwrite || !current ? hints.courseName || current : current));
    }
    if (hints.college) {
      setCollege((current) => (overwrite || !current ? hints.college || current : current));
    }
    if (hints.department) {
      setDepartment((current) => (overwrite || !current ? hints.department || current : current));
    }
    if (hints.year) {
      setYear((current) => (overwrite || !current ? hints.year || current : current));
    }
    if (hints.yearOfStudy) {
      setYearOfStudy((current) => (overwrite || !current ? hints.yearOfStudy || current : current));
    }
    if (hints.semester) {
      setSemester((current) => (overwrite || !current ? hints.semester || current : current));
    }
    if (hints.paperType) {
      setPaperType((current) => (overwrite || !current ? hints.paperType || current : current));
    }
    if (hints.lecturer) {
      setLecturer((current) => (overwrite || !current ? hints.lecturer || current : current));
    }
  };

  const handleCourseOptionChange = (value: string) => {
    setSelectedCourseOption(value);
    if (value === CUSTOM_COURSE_OPTION) {
      setCourseCode('');
      return;
    }

    const selectedPaper = knownCourseOptions.find((paper) => paper.course_code.toUpperCase() === value);
    if (selectedPaper) {
      applySuggestion(selectedPaper);
    } else {
      setCourseCode(value);
    }
  };

  const handleFileSelection = (
    file: File | null,
    setFile: React.Dispatch<React.SetStateAction<File | null>>,
    label: string,
    onAccepted?: (file: File) => void
  ) => {
    if (!file) {
      setFile(null);
      if (label === 'Paper file') {
        setDetectedHints(null);
        setSuggestionFeedback(null);
        lastAnalyzedPaperKeyRef.current = null;
      }
      return;
    }
    if (!isPdfFile(file)) {
      toast.error(`${label} must be a PDF file.`);
      return;
    }
    setFile(file);
    if (label === 'Paper file') {
      setDetectedHints(null);
      setSuggestionFeedback({ tone: 'info', message: 'Paper uploaded. We are checking it for suggested details.' });
      lastAnalyzedPaperKeyRef.current = null;
    }
    onAccepted?.(file);
  };

  const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

  const analyzePaperFile = async (file: File, manualRetry = false) => {
    setAnalyzingPaperFile(true);
    setSuggestionFeedback({
      tone: 'info',
      message: manualRetry
        ? 'Retrying paper analysis with a deeper suggestion pass...'
        : 'Reading your PDF and preparing suggestions...',
    });

    for (let attempt = 0; attempt < MAX_SUGGESTION_AUTO_RETRIES; attempt += 1) {
      try {
        let previewText = '';
        try {
          const analysis = await extractUploadPdfText(file);
          previewText = analysis.text;
          if (!analysis.has_readable_text) {
            setSuggestionFeedback({ tone: 'info', message: 'The PDF has little selectable text. We are checking the filename and available course matches too...' });
            previewText = await extractPdfPreviewText(file);
          }
        } catch (serverError) {
          console.warn('Server PDF analysis unavailable; using browser fallback:', serverError);
          previewText = await extractPdfPreviewText(file);
        }
        const hints = buildDetectedHints(file, previewText, knownCourseOptions);
        setDetectedHints(hints);

        if (!hints) {
          if (attempt < MAX_SUGGESTION_AUTO_RETRIES - 1) {
            setSuggestionFeedback({
              tone: 'info',
              message: `We are making another suggestion attempt (${attempt + 2}/${MAX_SUGGESTION_AUTO_RETRIES}) to improve the result...`,
            });
            await sleep(SUGGESTION_RETRY_DELAYS_MS[attempt]);
            continue;
          }

          setSuggestionFeedback({
            tone: 'warning',
            message: 'We tried several times, but we still could not confidently suggest details. Please review the fields manually or retry analysis.',
            canRetry: true,
            retryLabel: 'Retry suggestion',
          });
          setAnalyzingPaperFile(false);
          return;
        }

        applyDetectedHints(hints);
        setSuggestionFeedback({
          tone: 'success',
          message: manualRetry
            ? 'Retry worked. We found suggested details from your PDF.'
            : 'We suggested details from your PDF. Review the fields before submitting.',
        });
        setAnalyzingPaperFile(false);
        return;
      } catch (error) {
        console.error(`Failed to analyze paper PDF on attempt ${attempt + 1}:`, error);

        if (attempt < MAX_SUGGESTION_AUTO_RETRIES - 1) {
          setSuggestionFeedback({
            tone: 'info',
            message: `Suggestion analysis hit a problem. Trying again (${attempt + 2}/${MAX_SUGGESTION_AUTO_RETRIES})...`,
          });
          await sleep(SUGGESTION_RETRY_DELAYS_MS[attempt]);
          continue;
        }

        setDetectedHints(null);
        setSuggestionFeedback({
          tone: 'warning',
          message: 'Automatic suggestions could not be generated after several attempts. You can retry, or continue by filling the fields manually.',
          canRetry: true,
          retryLabel: 'Retry suggestion',
        });
        setAnalyzingPaperFile(false);
        return;
      } finally {
        if (attempt === MAX_SUGGESTION_AUTO_RETRIES - 1) {
          setAnalyzingPaperFile(false);
        }
      }
    }

    setAnalyzingPaperFile(false);
    setUploadProgress(0);
    setUploadStage(null);
  };

  const resetForm = () => {
    setSuccess(false);
    setUploadedPaper(null);
    setUploadedBook(null);
    setUploadKind('paper');
    setSelectedCourseOption(CUSTOM_COURSE_OPTION);
    setDetectedHints(null);
    setSuggestionFeedback(null);
    setAnalyzingPaperFile(false);
    lastAnalyzedPaperKeyRef.current = null;
    setTitle('');
    setCourseCode('');
    setCourseName('');
    setCollege('');
    setDepartment('');
    setYear('');
    setYearOfStudy('');
    setSemester('');
    setPaperType('');
    setLecturer('');
    setDescription('');
    setPaperFile(null);
    setSolutionFile(null);
    setBookTitle(''); setBookDescription(''); setBookIsbn(''); setBookEdition(''); setBookYear(''); setBookYearOfStudy(''); setBookSemester(''); setBookLanguage(''); setBookPublisher(''); setBookCategory(''); setBookSubject(''); setBookAuthors([]); setAuthorInput(''); setBookCourses([]); setCourseQuery(''); setBookModules([]); setModuleQuery(''); setBookFile(null); setBookCover(null);
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user) return;

    const hasStructuredContext = Boolean(academic.campus_id && academic.college_id && academic.school_id);
    if (!title || !courseCode || !courseName || (!hasStructuredContext && (!college || !department)) || !year || !paperType) {
      toast.error('Please fill in all required fields');
      return;
    }

    if (!paperFile) {
      toast.error('Please upload the paper PDF before submitting.');
      return;
    }

    if (!isPdfFile(paperFile)) {
      toast.error('Paper file must be a PDF.');
      return;
    }

    if (solutionFile && !isPdfFile(solutionFile)) {
      toast.error('Solution file must be a PDF.');
      return;
    }

    try {
      setSubmitting(true);
      setUploadStage('paper');
      setUploadProgress(0);

      let fileKey = '';
      let solutionKey = '';
      const paperUploadEnd = solutionFile ? 78 : 95;

      // Upload paper file
      const objectKey = buildStorageKey('papers', 'papers', paperFile.name, `${courseCode}-${paperType}-${year}-${Date.now()}`);
      try {
        fileKey = await uploadFileObject('papers', objectKey, paperFile, (percentage) => setUploadProgress(Math.round(percentage * paperUploadEnd / 100)));
      } catch (err) {
        console.error('File upload failed:', err);
        toast.error(normalizeApiError(err).message || 'Paper upload failed');
        return;
      }

      // Upload solution file
      if (solutionFile) {
        const solKey = buildStorageKey('papers', 'solutions', solutionFile.name, `${courseCode}-${paperType}-${year}-sol-${Date.now()}`);
        try {
          setUploadStage('solution');
          setUploadProgress(78);
          solutionKey = await uploadFileObject('papers', solKey, solutionFile, (percentage) => setUploadProgress(78 + Math.round(percentage * 0.17)));
        } catch (err) {
          console.error('Solution upload failed:', err);
        }
      }

      // Create paper record
      setUploadStage('publishing');
      setUploadProgress(96);
      const createdPaper = await createPaper({
        title: normalizeUserText(title) || title,
        course_code: normalizeUserText(courseCode)?.toUpperCase() || courseCode.toUpperCase(),
        course_name: normalizeUserText(courseName) || courseName,
        college: normalizeUserText(college) || college,
        department: normalizeUserText(department) || department,
        year: parseInt(year),
        year_of_study: yearOfStudy || undefined,
        semester: semester || undefined,
        paper_type: paperType,
        lecturer: normalizeUserText(lecturer) || lecturer || undefined,
        description: normalizeUserText(description),
        file_key: fileKey || undefined,
        solution_key: solutionKey || undefined,
        ...academic,
        programme_name_other: academic.programme_id === 'other' ? programmeNameOther : undefined,
      });

      setUploadedPaper(createdPaper);
      setUploadProgress(100);
      setSuccess(true);
      toast.success('Paper uploaded successfully!');
    } catch (err) {
      console.error('Upload failed:', err);
      toast.error(normalizeApiError(err).message || 'Failed to upload paper');
    } finally {
      setSubmitting(false);
      setUploadStage(null);
    }
  };

  const handleBookUpload = async (event: React.FormEvent) => {
    event.preventDefault();
    const authors = bookAuthors.map((author) => author.name);
    const courseIds = bookCourses.map((course) => course.id);
    if (!bookTitle.trim() || !bookLanguage || !authors.length || !courseIds.length || !bookFile || !bookCover) {
      toast.error('Title, language, authors, related courses, cover, and book file are required.');
      return;
    }
    const isBookDocument = /\.(pdf|epub)$/i.test(bookFile.name) || ['application/pdf', 'application/epub+zip'].includes(bookFile.type);
    if (!isBookDocument || !bookCover.type.startsWith('image/')) {
      toast.error('Use a PDF or EPUB book file and an image cover.');
      return;
    }
    try {
      setSubmitting(true); setUploadProgress(0); setUploadStage('paper');
      const stamp = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const bookKey = buildStorageKey('books', 'books', bookFile.name, stamp);
      await uploadFileObject('books', bookKey, bookFile, (percent) => setUploadProgress(Math.round(percent * 0.7)));
      setUploadStage('solution'); setUploadProgress(70);
      const coverKey = buildStorageKey('books', 'book-covers', bookCover.name, stamp);
      await uploadFileObject('books', coverKey, bookCover, (percent) => setUploadProgress(70 + Math.round(percent * 0.25)));
      setUploadStage('publishing'); setUploadProgress(96);
      const created = await createBook({
        title: normalizeUserText(bookTitle) || bookTitle, description: normalizeUserText(bookDescription), isbn: normalizeIsbn(bookIsbn), edition: normalizeUserText(bookEdition),
        publication_year: bookYear ? Number(bookYear) : undefined,
        year_of_study: bookYearOfStudy || undefined,
        semester: bookSemester || undefined,
        language: bookLanguage || undefined, publisher: bookPublisher || undefined,
        // CP/Admin uploads are published as public academic resources. The
        // public catalogue deliberately returns only active + public Books.
        category: normalizeUserText(bookCategory), subject: normalizeUserText(bookSubject), status: 'active', visibility: 'public', authors: normalizeUnique(authors), course_ids: normalizeUnique(courseIds), module_ids: normalizeUnique(bookModules.map((module) => module.id)),
        file: { key: bookKey, original_filename: bookFile.name, mime_type: bookFile.type, size: bookFile.size },
        cover: { key: coverKey, original_filename: bookCover.name, mime_type: bookCover.type, size: bookCover.size },
      });
      setUploadedBook(created); setUploadProgress(100); setSuccess(true); toast.success('Book uploaded successfully!');
    } catch (error) {
      toast.error(normalizeApiError(error).message || 'Failed to upload book');
    } finally { setSubmitting(false); setUploadStage(null); }
  };

  if (authLoading || siteAccessLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="theme-spinner h-8 w-8 animate-spin rounded-full border-b-2 border-current" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <img
          src="/assets/illustrations/document-upload.svg"
          alt="Academic document upload"
          className="w-48 h-48 mx-auto mb-6 rounded-lg opacity-80"
        />
        <h2 className="theme-title mb-4 text-2xl font-bold">Sign In Required</h2>
        <p className="theme-muted mb-6">
          You need to sign in to upload papers and contribute to the community.
        </p>
        <Button
          onClick={() => authApi.login('/upload')}
          className="theme-accent-bg"
        >
          Sign In to Upload
        </Button>
      </div>
    );
  }

  if (siteAccessError) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <h2 className="theme-title mb-4 text-2xl font-bold">Upload access unavailable</h2>
        <p className="theme-muted mb-6">
          Unable to load upload access settings. Please try again.
        </p>
        <Button onClick={() => window.location.reload()} className="theme-accent-bg">Try Again</Button>
      </div>
    );
  }

  if (!canAccessUploadArea) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <h2 className="theme-title mb-4 text-2xl font-bold">Uploads unavailable</h2>
        <p className="theme-muted mb-6">
          Upload access is currently disabled for your account or no upload resource types are enabled.
        </p>
        <Button onClick={() => navigate('/')} className="theme-accent-bg">Return Home</Button>
      </div>
    );
  }

  if (success) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <div className="theme-soft-panel mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-full text-success-foreground">
          <CheckCircle className="h-10 w-10" />
        </div>
        <h2 className="theme-title mb-4 text-2xl font-bold">Paper received successfully</h2>
        <p className="theme-muted mb-6">
          {uploadedBook ? `“${uploadedBook.title}” has been uploaded. Your management window is calculated securely by the server.` : `Your paper and its metadata have been safely stored with a ${uploadedPaper?.verification_status || inferVerificationStatus()} verification status. Academic processing is continuing in the background so Study AI can understand its pages, text, questions and sections.`}
          {profile?.requested_role_status === 'pending'
            ? ` Your ${profile.requested_role || 'special access'} request is still pending, so this upload was handled as a normal community upload.`
            : ' You do not need to keep this page open; Study AI will become fully available when processing is complete. Thank you for contributing!'}
        </p>
        <div className="flex gap-3 justify-center">
          <Button onClick={resetForm} variant="outline">
            Upload Another
          </Button>
          <Button onClick={() => navigate('/dashboard')} className="theme-accent-bg">
            Go to Dashboard
          </Button>
        </div>
      </div>
    );
  }

  if (uploadKind === 'book') {
    return <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <Button type="button" variant="ghost" onClick={() => navigate(-1)} className="theme-muted mb-6 hover:bg-transparent hover:text-primary"><ArrowLeft className="h-4 w-4 mr-2" />Back</Button>
      <Card className="theme-panel"><CardHeader><CardTitle className="theme-title flex items-center gap-2"><UploadIcon className="theme-section-icon h-6 w-6" />Upload</CardTitle><div className="mt-4 grid grid-cols-2 rounded-lg border p-1">{enabledUploadKinds.includes('paper') ? <Button type="button" variant={selectedUploadKind === 'paper' ? 'default' : 'ghost'} className={selectedUploadKind === 'paper' ? 'theme-accent-bg' : ''} onClick={() => setUploadKind('paper')}>📄 Paper</Button> : <div />}{enabledUploadKinds.includes('book') ? <Button type="button" variant={selectedUploadKind === 'book' ? 'default' : 'ghost'} className={selectedUploadKind === 'book' ? 'theme-accent-bg' : ''} onClick={() => setUploadKind('book')}>📚 Book</Button> : <div />}</div></CardHeader><CardContent>
        <form onSubmit={handleBookUpload} className="space-y-6">
          <div className="theme-soft-panel rounded-lg p-4 text-sm"><p className="theme-title flex items-center gap-2 font-medium"><Sparkles className="h-4 w-4" />Book upload</p><p className="theme-muted mt-2">Add the book file, cover, and catalogue details. Your account is automatically recorded as the uploader.</p></div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2"><Label className="theme-form-label">Book title *</Label><Input className="theme-form-input mt-1" value={bookTitle} onChange={(e) => setBookTitle(e.target.value)} placeholder="e.g., Database System Concepts" required aria-invalid={!bookTitle.trim()} /> <InlineFieldMessage message={!bookTitle.trim() ? 'Title is required.' : undefined} /></div>
            <div><Label className="theme-form-label">ISBN</Label><Input className="theme-form-input mt-1" value={bookIsbn} onChange={(e) => setBookIsbn(e.target.value)} /><InlineFieldMessage message={bookIsbn.trim() && !normalizeIsbn(bookIsbn) ? 'Enter a valid ISBN or leave this optional field blank.' : undefined} /></div><div><Label className="theme-form-label">Edition</Label><Input className="theme-form-input mt-1" value={bookEdition} onChange={(e) => setBookEdition(e.target.value)} /></div>
            <div><Label className="theme-form-label">Publication year</Label><Input className="theme-form-input mt-1" type="number" value={bookYear} onChange={(e) => setBookYear(e.target.value)} /></div><div><Label className="theme-form-label">Language *</Label><Select value={bookLanguage} onValueChange={setBookLanguage}><SelectTrigger className="theme-form-input mt-1"><SelectValue placeholder="Select language" /></SelectTrigger><SelectContent>{[['en','English'],['fr','French'],['rw','Kinyarwanda'],['sw','Swahili'],['ar','Arabic'],['zh','Chinese'],['es','Spanish'],['pt','Portuguese'],['de','German'],['it','Italian'],['ja','Japanese'],['ko','Korean'],['hi','Hindi'],['ru','Russian'],['other','Other']].map(([value,label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent></Select></div>
            <div>
              <Label className="theme-form-label">Target Study Year (Optional)</Label>
              <Select value={bookYearOfStudy} onValueChange={setBookYearOfStudy}>
                <SelectTrigger className="theme-form-input mt-1">
                  <SelectValue placeholder="Select Study Year" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Not specified</SelectItem>
                  {STUDY_YEARS.map((y) => (
                    <SelectItem key={y} value={y}>{y}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="theme-form-label">Semester (Optional)</Label>
              <Select value={bookSemester} onValueChange={setBookSemester}>
                <SelectTrigger className="theme-form-input mt-1">
                  <SelectValue placeholder="Select Semester" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Not specified</SelectItem>
                  {SEMESTERS.map((s) => (
                    <SelectItem key={s} value={s}>{s}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div><Label className="theme-form-label">Publisher</Label><Input className="theme-form-input mt-1" value={bookPublisher} onChange={(e) => setBookPublisher(e.target.value)} /></div><div><Label className="theme-form-label">Category</Label><Input className="theme-form-input mt-1" value={bookCategory} onChange={(e) => setBookCategory(e.target.value)} /></div>
            <div className="sm:col-span-2"><Label className="theme-form-label">Subject</Label><Input className="theme-form-input mt-1" value={bookSubject} onChange={(e) => setBookSubject(e.target.value)} /></div>
          </div>
            <div><Label className="theme-form-label">Authors *</Label><div className="mt-1 flex gap-2"><Input className="theme-form-input" value={authorInput} onChange={(e) => setAuthorInput(e.target.value)} placeholder="Author name" /><Button type="button" variant="outline" onClick={() => { const name = authorInput.trim(); if (name && !bookAuthors.some((author) => author.name === name)) { setBookAuthors((current) => [...current, { name }]); setAuthorInput(''); } }}>+ Add Author</Button></div><InlineFieldMessage message={!bookAuthors.length ? 'Add at least one author.' : undefined} /><div className="mt-2 flex flex-wrap gap-2">{bookAuthors.map((author) => <span key={author.name} className="rounded-full bg-muted px-3 py-1 text-sm">{author.name}<button type="button" className="ml-2" onClick={() => setBookAuthors((current) => current.filter((item) => item.name !== author.name))}>×</button></span>)}</div></div>
          <div><Label className="theme-form-label">Related courses *</Label><Input className="theme-form-input mt-1" value={courseQuery} onChange={(e) => { const query = e.target.value; setCourseQuery(query); if (query.trim()) void searchCourses(query).then((data) => setCourseOptions(data.items)); else setCourseOptions([]); }} placeholder="Search course code or name..." />{courseOptions.length > 0 && <div className="mt-2 space-y-1 rounded border p-2">{courseOptions.filter((course) => !bookCourses.some((selected) => selected.id === course.id)).map((course) => <button className="block w-full rounded px-2 py-1 text-left text-sm hover:bg-muted" key={course.id} type="button" onClick={() => { setBookCourses((selected) => selected.some((item) => item.id === course.id) ? selected : [...selected, course]); setCourseQuery(''); setCourseOptions([]); }}>{course.code || 'No code'} — {course.name}</button>)}</div>}<div className="mt-2 grid gap-2 sm:grid-cols-3"><Input className="theme-form-input" value={newCourseCode} onChange={(e) => setNewCourseCode(e.target.value)} placeholder="Course code" /><Input className="theme-form-input" value={newCourseDescription} onChange={(e) => setNewCourseDescription(e.target.value)} placeholder="Description (optional)" /><Button type="button" variant="outline" disabled={!courseQuery.trim()} onClick={async () => { const course = await createCourse({ name: courseQuery.trim(), code: newCourseCode || undefined, description: newCourseDescription || undefined }); setBookCourses((selected) => selected.some((item) => item.id === course.id) ? selected : [...selected, course]); setCourseQuery(''); setNewCourseCode(''); setNewCourseDescription(''); }}>+ Add Course</Button></div><div className="mt-2 flex flex-wrap gap-2">{bookCourses.map((course) => <span key={course.id} className="rounded-full bg-muted px-3 py-1 text-sm">{course.code || '—'} — {course.name}<button type="button" className="ml-2" onClick={() => setBookCourses((selected) => selected.filter((item) => item.id !== course.id))}>×</button></span>)}</div></div>
          <div><Label className="theme-form-label">Related modules</Label><div className="mt-1 flex gap-2"><Input className="theme-form-input" value={moduleQuery} onChange={(e) => { setModuleQuery(e.target.value); void fetchModules(e.target.value).then((data) => setModuleOptions(data.items)); }} placeholder="Search module" /><Button type="button" variant="outline" onClick={async () => { const name = moduleQuery.trim(); if (!name) return; const module = await createModule({ name, code: newModuleCode || undefined, description: newModuleDescription || undefined, course_id: bookCourses[0]?.id }); setBookModules((selected) => selected.some((item) => item.id === module.id) ? selected : [...selected, module]); setModuleQuery(''); setNewModuleCode(''); setNewModuleDescription(''); }}>+ Add Module</Button></div>{moduleOptions.length > 0 && <div className="mt-2 flex flex-wrap gap-2">{moduleOptions.map((module) => <Button key={module.id} type="button" size="sm" variant="outline" onClick={() => setBookModules((selected) => selected.some((item) => item.id === module.id) ? selected : [...selected, module])}>{module.name}</Button>)}</div>}<div className="mt-2 grid gap-2 sm:grid-cols-2"><Input className="theme-form-input" value={newModuleCode} onChange={(e) => setNewModuleCode(e.target.value)} placeholder="New module code (optional)" /><Input className="theme-form-input" value={newModuleDescription} onChange={(e) => setNewModuleDescription(e.target.value)} placeholder="New module description (optional)" /></div><div className="mt-2 flex flex-wrap gap-2">{bookModules.map((module) => <span key={module.id} className="rounded-full bg-muted px-3 py-1 text-sm">{module.name}<button type="button" className="ml-2" onClick={() => setBookModules((selected) => selected.filter((item) => item.id !== module.id))}>×</button></span>)}</div></div>
          <div><Label className="theme-form-label">Description</Label><Textarea className="theme-form-input mt-1" value={bookDescription} onChange={(e) => setBookDescription(e.target.value)} rows={3} placeholder="Brief description of the book..." /></div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div><Label className="theme-form-label">Book file (PDF or EPUB) *</Label><div className={`theme-dropzone mt-1 rounded-lg p-4 text-center transition-colors ${submitting && uploadStage === 'paper' ? 'file-upload-card--transferring' : ''} ${bookFileDragActive ? 'theme-dropzone--active' : ''}`} onClick={() => document.getElementById('bookFile')?.click()} onDragOver={(e) => handleDragOver(e, setBookFileDragActive)} onDragEnter={(e) => handleDragOver(e, setBookFileDragActive)} onDragLeave={(e) => handleDragLeave(e, setBookFileDragActive)} onDrop={(e) => { e.preventDefault(); setBookFileDragActive(false); setBookFile(e.dataTransfer.files?.[0] || null); }}><input id="bookFile" className="hidden" type="file" accept=".pdf,.epub,application/pdf,application/epub+zip" onChange={(e) => setBookFile(e.target.files?.[0] || null)} /><label htmlFor="bookFile" className="cursor-pointer"><FileText className="mx-auto mb-2 h-8 w-8 text-muted-foreground" /><p className="theme-muted text-sm">{bookFile ? `${bookFile.name} · ${(bookFile.size / 1024 / 1024).toFixed(2)} MB` : 'Click to choose book file'}</p><p className="theme-muted mt-1 text-xs">PDF or EPUB</p></label></div></div>
            <div><Label className="theme-form-label">Book cover *</Label><div className={`theme-dropzone mt-1 rounded-lg p-4 text-center transition-colors ${submitting && uploadStage === 'solution' ? 'file-upload-card--transferring' : ''} ${bookCoverDragActive ? 'theme-dropzone--active' : ''}`} onClick={() => document.getElementById('bookCover')?.click()} onDragOver={(e) => handleDragOver(e, setBookCoverDragActive)} onDragEnter={(e) => handleDragOver(e, setBookCoverDragActive)} onDragLeave={(e) => handleDragLeave(e, setBookCoverDragActive)} onDrop={(e) => { e.preventDefault(); setBookCoverDragActive(false); setBookCover(e.dataTransfer.files?.[0] || null); }}><input id="bookCover" className="hidden" type="file" accept="image/*" onChange={(e) => setBookCover(e.target.files?.[0] || null)} /><label htmlFor="bookCover" className="cursor-pointer">{bookCover?.type.startsWith('image/') ? <img className="mx-auto mb-2 h-16 w-12 rounded object-cover" src={URL.createObjectURL(bookCover)} alt="Book cover preview" /> : <UploadIcon className="mx-auto mb-2 h-8 w-8 text-muted-foreground" />}<p className="theme-muted text-sm">{bookCover ? bookCover.name : 'Click to choose cover image'}</p><p className="theme-muted mt-1 text-xs">Image file</p></label></div></div>
          </div>
          {submitting && <div className="upload-progress-panel rounded-2xl border p-5"><div className="flex items-start gap-4"><div className="upload-progress-orb flex h-12 w-12 shrink-0 items-center justify-center rounded-full" style={{ '--upload-progress': `${uploadProgress}%` } as React.CSSProperties}><span className="rounded-full bg-background px-1 text-xs font-bold">{uploadProgress}%</span></div><div><p className="theme-title flex items-center gap-2 font-semibold"><LoaderCircle className="h-4 w-4 animate-spin text-primary" />{uploadStage === 'solution' ? 'Uploading book cover' : uploadStage === 'publishing' ? 'Saving book details' : 'Uploading book file'}</p><p className="theme-muted mt-1 text-sm">Please keep this page open while we securely transfer your book.</p></div></div></div>}
          <div className="theme-accent-soft-border rounded-lg border-dashed p-4 text-sm"><p className="theme-title font-medium">Review Book</p><div className="theme-muted mt-2 grid gap-1 sm:grid-cols-2"><p>Title: <span className="text-foreground">{bookTitle || '—'}</span></p><p>Language: <span className="text-foreground">{bookLanguage || '—'}</span></p><p>Study Year: <span className="text-foreground">{bookYearOfStudy && bookYearOfStudy !== 'none' ? bookYearOfStudy : '—'}</span></p><p>Semester: <span className="text-foreground">{bookSemester && bookSemester !== 'none' ? bookSemester : '—'}</span></p><p>Authors: <span className="text-foreground">{bookAuthors.map((author) => author.name).join(', ') || '—'}</span></p><p>Courses: <span className="text-foreground">{bookCourses.map((course) => `${course.code || '—'} — ${course.name}`).join(', ') || '—'}</span></p><p>Modules: <span className="text-foreground">{bookModules.map((module) => module.name).join(', ') || '—'}</span></p><p>File: <span className="text-foreground">{bookFile?.name || '—'}</span></p><p>Cover: <span className="text-foreground">{bookCover ? 'Selected' : '—'}</span></p><p>Uploaded by: <span className="text-foreground">{user.name || user.email}</span></p></div><p className="theme-muted mt-2">The server assigns ownership and the 48-hour CP management deadline.</p></div>
          <InlineFieldMessage message={!bookLanguage ? 'Select a language.' : !bookCourses.length ? 'Select at least one course.' : !bookFile ? 'Choose the book file.' : !bookCover ? 'Choose a cover image.' : undefined} />
          <Button type="submit" disabled={submitting} className="theme-accent-bg h-12 w-full text-lg">{submitting ? <><LoaderCircle className="mr-2 h-5 w-5 animate-spin" />Uploading...</> : <><UploadIcon className="mr-2 h-5 w-5" />Upload Book</>}</Button>
        </form>
      </CardContent></Card>
    </div>;
  }

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <Button variant="ghost" onClick={() => navigate(-1)} className="theme-muted mb-6 hover:bg-transparent hover:text-primary">
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back
      </Button>

      <Card className="theme-panel">
        <CardHeader>
          <CardTitle className="theme-title flex items-center gap-2">
            <UploadIcon className="theme-section-icon h-6 w-6" />
            Upload
          </CardTitle>
          <div className="mt-4 grid grid-cols-2 rounded-lg border p-1">{enabledUploadKinds.includes('paper') ? <Button type="button" variant={selectedUploadKind === 'paper' ? 'default' : 'ghost'} className={selectedUploadKind === 'paper' ? 'theme-accent-bg' : ''} onClick={() => setUploadKind('paper')}>📄 Paper</Button> : <div />}{enabledUploadKinds.includes('book') ? <Button type="button" variant={selectedUploadKind === 'book' ? 'default' : 'ghost'} className={selectedUploadKind === 'book' ? 'theme-accent-bg' : ''} onClick={() => setUploadKind('book')}>📚 Book</Button> : <div />}</div>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleUpload} className="space-y-6">
            <div className="theme-soft-panel rounded-lg p-4 text-sm">
              <p className="theme-title flex items-center gap-2 font-medium">
                <Sparkles className="h-4 w-4" />
                Smart upload helper
              </p>
              <p className="theme-muted mt-2">
                Upload the paper PDF first and we will try to suggest the title, course, year, paper type, and lecturer from the filename and readable PDF text.
              </p>
            </div>

            <div>
              <Label className="theme-form-label">Paper File (PDF only) *</Label>
              <div
                className={`theme-dropzone mt-1 rounded-lg p-4 text-center transition-colors ${submitting && uploadStage === 'paper' ? 'file-upload-card--transferring' : ''} ${paperDragActive ? 'theme-dropzone--active' : ''}`}
                onClick={() => document.getElementById('paperFile')?.click()}
                onDragOver={(e) => handleDragOver(e, setPaperDragActive)}
                onDragEnter={(e) => handleDragOver(e, setPaperDragActive)}
                onDragLeave={(e) => handleDragLeave(e, setPaperDragActive)}
                onDrop={(e) => handleDropFile(e, setPaperFile, setPaperDragActive, 'Paper file')}
              >
                <input type="file" accept=".pdf" onChange={(e) => handleFileSelection(e.target.files?.[0] || null, setPaperFile, 'Paper file')} className="hidden" id="paperFile" />
                <label htmlFor="paperFile" className="cursor-pointer">
                  <FileText className="mx-auto mb-2 h-8 w-8 text-muted-foreground" />
                  <p className="theme-muted text-sm">{paperFile ? paperFile.name : 'Click to upload paper'}</p>
                  <p className="theme-muted mt-1 text-xs">Only `.pdf` files are accepted. We will automatically suggest details from this file.</p>
                </label>
              </div>
            </div>

            {suggestionFeedback && !analyzingPaperFile && (
              <div
                className={`rounded-lg p-4 text-sm ${
                  suggestionFeedback.tone === 'success'
                    ? 'border border-success-border bg-success-soft text-success-foreground'
                    : suggestionFeedback.tone === 'warning'
                      ? 'border border-warning-border bg-warning-soft text-warning-foreground'
                      : 'theme-soft-panel'
                }`}
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <p>{suggestionFeedback.message}</p>
                  {suggestionFeedback.canRetry && paperFile && (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        lastAnalyzedPaperKeyRef.current = null;
                        void analyzePaperFile(paperFile, true);
                      }}
                    >
                      {suggestionFeedback.retryLabel || 'Retry'}
                    </Button>
                  )}
                </div>
              </div>
            )}

            {/* Title */}
            <div>
              <Label htmlFor="title" className="theme-form-label">Paper Title *</Label>
              <Input
                id="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g., Data Structures - Final Exam 2024"
                className="theme-form-input mt-1"
                required
              />
            </div>

            {analyzingPaperFile && (
              <div className="theme-soft-panel rounded-lg p-4 text-sm">
                <p className="theme-title flex items-center gap-2 font-medium">
                  <Sparkles className="h-4 w-4" />
                  Reading your PDF for suggestions...
                </p>
                <p className="theme-muted mt-2">
                  We are scanning the uploaded file to suggest the most likely course details.
                </p>
              </div>
            )}

            {detectedHints && !analyzingPaperFile && (
              <div className="theme-soft-panel rounded-lg p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="theme-title flex items-center gap-2 text-sm font-medium">
                      <Sparkles className="h-4 w-4" />
                      Suggestions from your uploaded PDF
                    </p>
                    <p className="theme-muted mt-2 text-sm">
                      We matched what we could from the filename and readable PDF text. Please review before submitting.
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button type="button" variant="outline" size="sm" onClick={() => applyDetectedHints(detectedHints, false)}>
                      Fill empty fields
                    </Button>
                    <Button type="button" size="sm" className="theme-accent-bg" onClick={() => applyDetectedHints(detectedHints, true)}>
                      Replace with suggestions
                    </Button>
                  </div>
                </div>
                <div className="mt-4 grid gap-2 text-sm text-muted-foreground sm:grid-cols-2">
                  {detectedHints.title && <p>Title: <span className="font-medium text-foreground">{detectedHints.title}</span></p>}
                  {detectedHints.courseCode && <p>Course code: <span className="font-medium text-foreground">{detectedHints.courseCode}</span></p>}
                  {detectedHints.courseName && <p>Course name: <span className="font-medium text-foreground">{detectedHints.courseName}</span></p>}
                  {detectedHints.year && <p>Year: <span className="font-medium text-foreground">{detectedHints.year}</span></p>}
                  {detectedHints.yearOfStudy && <p>Study Year: <span className="font-medium text-foreground">{detectedHints.yearOfStudy}</span></p>}
                  {detectedHints.semester && <p>Semester: <span className="font-medium text-foreground">{detectedHints.semester}</span></p>}
                  {detectedHints.paperType && <p>Paper type: <span className="font-medium text-foreground">{detectedHints.paperType}</span></p>}
                  {detectedHints.lecturer && <p>Lecturer: <span className="font-medium text-foreground">{detectedHints.lecturer}</span></p>}
                </div>
                {detectedHints.evidence.length > 0 && (
                  <div className="mt-4 rounded-lg border border-border/70 bg-background/60 p-3">
                    <p className="theme-title text-xs font-medium uppercase tracking-wide">Why we suggested this</p>
                    <div className="mt-2 space-y-1 text-sm text-muted-foreground">
                      {detectedHints.evidence.slice(0, 4).map((item) => (
                        <p key={item}>- {item}</p>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Course Info */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label className="theme-form-label">Course Code Option *</Label>
                <Select value={selectedCourseOption} onValueChange={handleCourseOptionChange}>
                  <SelectTrigger className="theme-form-input mt-1">
                    <SelectValue placeholder="Choose a known course or custom code" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={CUSTOM_COURSE_OPTION}>Custom course code</SelectItem>
                    {knownCourseOptions.map((paper) => (
                      <SelectItem key={paper.course_code.toUpperCase()} value={paper.course_code.toUpperCase()}>
                        {paper.course_code.toUpperCase()} - {paper.course_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="theme-muted mt-2 text-xs">
                  Pick an existing course to reuse its details, or choose custom if you need a new course code.
                </p>
              </div>
              <div>
                <Label htmlFor="courseName" className="theme-form-label">Course Name *</Label>
                <Input
                  id="courseName"
                  value={courseName}
                  onChange={(e) => setCourseName(e.target.value)}
                  placeholder="e.g., Data Structures and Algorithms"
                  className="theme-form-input mt-1"
                  required
                />
              </div>
            </div>

            {selectedCourseOption === CUSTOM_COURSE_OPTION && (
              <div>
                <Label htmlFor="courseCode" className="theme-form-label">Custom Course Code *</Label>
                <Input
                  id="courseCode"
                  value={courseCode}
                  onChange={(e) => setCourseCode(e.target.value.toUpperCase())}
                  placeholder="e.g., CSC2101"
                  className="theme-form-input mt-1"
                  required
                />
                <p className="theme-muted mt-2 text-xs">Enter the exact course code if it does not appear in the list.</p>
              </div>
            )}

            {matchingSuggestions.length > 0 && (
              <div className="theme-soft-panel rounded-lg p-4">
                <p className="theme-title mb-3 text-sm font-medium">Auto-suggested course details</p>
                <div className="flex flex-wrap gap-2">
                  {matchingSuggestions.map((paper) => (
                    <button
                      key={paper.id}
                      type="button"
                      onClick={() => applySuggestion(paper)}
                      className="theme-accent-soft-border rounded-full px-3 py-1 text-xs transition-colors hover:bg-primary hover:text-primary-foreground"
                    >
                      {paper.course_code} · {paper.course_name}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <AcademicContextFields value={academic} onChange={setAcademic} otherName={programmeNameOther} onOtherNameChange={setProgrammeNameOther} title="Academic context" paper submissionSource="paper_upload" />
            {/* Legacy fallback for material outside the verified catalogue. */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label className="theme-form-label">Legacy college {academic.college_id ? '(optional)' : '*'}</Label>
                <Input value={college} onChange={(event) => setCollege(event.target.value)} placeholder="Only if not represented above" className="theme-form-input mt-1" />
              </div>
              <div>
                <Label className="theme-form-label">Legacy department {academic.school_id ? '(optional)' : '*'}</Label>
                <Input value={department} onChange={(event) => setDepartment(event.target.value)} placeholder="Only if not represented above" className="theme-form-input mt-1" />
              </div>
            </div>

            {/* Year & Type */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label className="theme-form-label">Academic Year *</Label>
                <Select value={year} onValueChange={setYear}>
                  <SelectTrigger className="theme-form-input mt-1">
                    <SelectValue placeholder="Select Year" />
                  </SelectTrigger>
                  <SelectContent>
                    {YEARS.map((y) => (
                      <SelectItem key={y} value={String(y)}>{y}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="theme-form-label">Paper Type *</Label>
                <Select value={paperType} onValueChange={setPaperType}>
                  <SelectTrigger className="theme-form-input mt-1">
                    <SelectValue placeholder="Select Type" />
                  </SelectTrigger>
                  <SelectContent>
                    {PAPER_TYPES.map((t) => (
                      <SelectItem key={t} value={t}>{t}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Study Year & Semester */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label className="theme-form-label">Study Year (Optional)</Label>
                <Select value={yearOfStudy} onValueChange={setYearOfStudy}>
                  <SelectTrigger className="theme-form-input mt-1">
                    <SelectValue placeholder="Select Study Year (e.g. Year 1, Year 2)" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Not specified</SelectItem>
                    {STUDY_YEARS.map((y) => (
                      <SelectItem key={y} value={y}>{y}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="theme-muted mt-1.5 text-xs">The curriculum year for which this assessment was set.</p>
              </div>
              <div>
                <Label className="theme-form-label">Semester (Optional)</Label>
                <Select value={semester} onValueChange={setSemester}>
                  <SelectTrigger className="theme-form-input mt-1">
                    <SelectValue placeholder="Select Semester (e.g. Semester 1, Semester 2)" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Not specified</SelectItem>
                    {SEMESTERS.map((s) => (
                      <SelectItem key={s} value={s}>{s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="theme-muted mt-1.5 text-xs">Semester or term period of the exam paper.</p>
              </div>
            </div>

            {/* Lecturer */}
            <div>
              <Label htmlFor="lecturer" className="theme-form-label">Lecturer (Optional)</Label>
              <Input
                id="lecturer"
                value={lecturer}
                onChange={(e) => setLecturer(e.target.value)}
                placeholder="e.g., Dr. Jean Baptiste Uwimana"
                className="theme-form-input mt-1"
              />
            </div>

            {/* Description */}
            <div>
              <Label htmlFor="description" className="theme-form-label">Description (Optional)</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Brief description of the paper content..."
                rows={3}
                className="theme-form-input mt-1"
              />
            </div>

            <div className="theme-accent-soft-border rounded-lg border-dashed p-4">
              <p className="theme-title text-sm font-medium">Upload status preview</p>
              <p className="theme-muted mt-1 text-sm">
                This upload will be marked as <span className="font-semibold">{inferVerificationStatus()}</span>
                {profile ? ` based on your role "${profile.role}" and trust score ${profile.trust_score || 0}.` : '.'}
              </p>
              {profile?.requested_role_status === 'pending' && (
                <p className="theme-muted mt-2 text-sm">
                  Your request for {profile.requested_role || 'special access'} is still pending, so this upload will remain a normal user upload until approval.
                </p>
              )}
            </div>

            {submitting && (
              <div className="upload-progress-panel rounded-2xl border p-5" role="status" aria-live="polite">
                <div className="flex items-start gap-4">
                  <div className="upload-progress-orb flex h-12 w-12 shrink-0 items-center justify-center rounded-full" style={{ '--upload-progress': `${uploadProgress}%` } as React.CSSProperties}>
                    <span className="rounded-full bg-background px-1 text-xs font-bold">{uploadProgress}%</span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="theme-title flex items-center gap-2 font-semibold"><LoaderCircle className="h-4 w-4 animate-spin text-primary" />
                      {uploadStage === 'solution' ? 'Uploading solution PDF' : uploadStage === 'publishing' ? 'Publishing your paper' : 'Uploading paper PDF'}
                    </p>
                    <p className="theme-muted mt-1 text-sm">
                      {uploadStage === 'publishing' ? 'Your files are secure. We are saving the paper details now.' : 'Please keep this page open while we safely transfer your document.'}
                    </p>
                    <div className="upload-progress-track mt-4 h-2 overflow-hidden rounded-full"><div className="upload-progress-fill h-full rounded-full" style={{ width: `${uploadProgress}%` }} /></div>
                  </div>
                </div>
              </div>
            )}

            {/* File Uploads */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label className="theme-form-label">Solution File (Optional PDF)</Label>
                <div
                  className={`theme-dropzone mt-1 rounded-lg p-4 text-center transition-colors ${submitting && uploadStage === 'solution' ? 'file-upload-card--transferring' : ''} ${
                    solutionDragActive
                      ? 'theme-dropzone--active'
                      : ''
                  }`}
                  onClick={() => document.getElementById('solutionFile')?.click()}
                  onDragOver={(e) => handleDragOver(e, setSolutionDragActive)}
                  onDragEnter={(e) => handleDragOver(e, setSolutionDragActive)}
                  onDragLeave={(e) => handleDragLeave(e, setSolutionDragActive)}
                  onDrop={(e) => handleDropFile(e, setSolutionFile, setSolutionDragActive, 'Solution file')}
                >
                  <input
                    type="file"
                    accept=".pdf"
                    onChange={(e) => handleFileSelection(e.target.files?.[0] || null, setSolutionFile, 'Solution file')}
                    className="hidden"
                    id="solutionFile"
                  />
                  <label htmlFor="solutionFile" className="cursor-pointer">
                    <FileText className="mx-auto mb-2 h-8 w-8 text-muted-foreground" />
                    <p className="theme-muted text-sm">
                      {solutionFile ? solutionFile.name : 'Click to upload solution'}
                    </p>
                    <p className="theme-muted mt-1 text-xs">Only `.pdf` files are accepted.</p>
                  </label>
                </div>
              </div>
            </div>

            <Button
              type="submit"
              disabled={submitting}
              className="theme-accent-bg h-12 w-full text-lg"
            >
              {submitting ? (
                <div className="flex items-center gap-2">
                  <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-primary-foreground" />
                  Uploading...
                </div>
              ) : (
                <>
                  <UploadIcon className="h-5 w-5 mr-2" />
                  Upload Paper
                </>
              )}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
