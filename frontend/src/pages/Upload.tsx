import { useState, useEffect, useRef, type DragEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { createPaper, fetchAllPapers, fetchUserProfile, uploadFileObject, type Paper, type UserProfile } from '../lib/client';
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
import { Upload as UploadIcon, FileText, ArrowLeft, CheckCircle, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import AcademicContextFields, { type AcademicContextValue } from '@/components/AcademicContextFields';

const PAPER_TYPES = ['Exam', 'CAT', 'Assignment', 'GroupWork'];

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
  paperType?: string;
  lecturer?: string;
  evidence: string[];
};

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function normalizeText(value: string) {
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

function buildDetectedHints(file: File, previewText: string, courseOptions: Paper[]): DetectedUploadHints | null {
  const filenameText = humanizeFileStem(file.name);
  const combinedText = `${filenameText} ${previewText}`;
  const normalizedCombined = normalizeText(combinedText);
  const evidence: string[] = [];
  const hints: DetectedUploadHints = { evidence };

  const courseByCode = [...courseOptions]
    .sort((left, right) => right.course_code.length - left.course_code.length)
    .find((paper) => new RegExp(`\\b${escapeRegExp(paper.course_code)}\\b`, 'i').test(combinedText));

  const courseByName =
    courseByCode ||
    courseOptions.find((paper) => {
      const normalizedCourseName = normalizeText(paper.course_name || '');
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

  const lecturer = detectLecturer(previewText);
  if (lecturer) {
    hints.lecturer = lecturer;
    evidence.push(`Detected lecturer name ${lecturer}.`);
  }

  if (matchedCourse?.course_name) {
    hints.title = `${matchedCourse.course_name} - ${hints.paperType || 'Paper'}${hints.year ? ` ${hints.year}` : ''}`;
  } else if (filenameText) {
    hints.title = filenameText;
    evidence.push('Built a draft title from the PDF filename.');
  }

  return evidence.length ? hints : null;
}

export default function UploadPage() {
  const navigate = useNavigate();
  const { user, loading } = useAuth();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [uploadedPaper, setUploadedPaper] = useState<Paper | null>(null);
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
  const [paperType, setPaperType] = useState('');
  const [lecturer, setLecturer] = useState('');
  const [description, setDescription] = useState('');
  const [paperFile, setPaperFile] = useState<File | null>(null);
  const [solutionFile, setSolutionFile] = useState<File | null>(null);
  const [paperDragActive, setPaperDragActive] = useState(false);
  const [solutionDragActive, setSolutionDragActive] = useState(false);

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
    if (['admin', 'content_manager', 'cp', 'lecturer'].includes(profile.role)) {
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
    if (!paperFile || analyzingPaperFile || knownCourseOptions.length === 0) return;
    const analysisKey = `${paperFile.name}:${paperFile.size}:${paperFile.lastModified}`;
    if (lastAnalyzedPaperKeyRef.current === analysisKey) return;
    lastAnalyzedPaperKeyRef.current = analysisKey;
    void analyzePaperFile(paperFile);
  }, [paperFile, analyzingPaperFile, knownCourseOptions.length]);

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
        const previewText = await extractPdfPreviewText(file);
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
  };

  const resetForm = () => {
    setSuccess(false);
    setUploadedPaper(null);
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
    setPaperType('');
    setLecturer('');
    setDescription('');
    setPaperFile(null);
    setSolutionFile(null);
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

      let fileKey = '';
      let solutionKey = '';

      // Upload paper file
      const objectKey = `${courseCode}_${paperType}_${year}_${Date.now()}.pdf`;
      try {
        await uploadFileObject('papers', objectKey, paperFile);
        fileKey = objectKey;
      } catch (err) {
        console.error('File upload failed:', err);
        toast.error('Paper upload failed');
        return;
      }

      // Upload solution file
      if (solutionFile) {
        const solKey = `solutions/${courseCode}_${paperType}_${year}_sol_${Date.now()}.pdf`;
        try {
          await uploadFileObject('papers', solKey, solutionFile);
          solutionKey = solKey;
        } catch (err) {
          console.error('Solution upload failed:', err);
        }
      }

      // Create paper record
      const createdPaper = await createPaper({
        title,
        course_code: courseCode.toUpperCase(),
        course_name: courseName,
        college,
        department,
        year: parseInt(year),
        paper_type: paperType,
        lecturer: lecturer || undefined,
        description: description || undefined,
        file_key: fileKey || undefined,
        solution_key: solutionKey || undefined,
        ...academic,
        programme_name_other: academic.programme_id === 'other' ? programmeNameOther : undefined,
      });

      setUploadedPaper(createdPaper);
      setSuccess(true);
      toast.success('Paper uploaded successfully!');
    } catch (err) {
      console.error('Upload failed:', err);
      toast.error('Failed to upload paper');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
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

  if (success) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <div className="theme-soft-panel mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-full text-success-foreground">
          <CheckCircle className="h-10 w-10" />
        </div>
        <h2 className="theme-title mb-4 text-2xl font-bold">Upload Successful!</h2>
        <p className="theme-muted mb-6">
          Your paper has been submitted with a {uploadedPaper?.verification_status || inferVerificationStatus()} verification status.
          {profile?.requested_role_status === 'pending'
            ? ` Your ${profile.requested_role || 'special access'} request is still pending, so this upload was handled as a normal community upload.`
            : ' Thank you for contributing!'}
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
            Upload Past Paper
          </CardTitle>
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

            {/* File Uploads */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label className="theme-form-label">Paper File (PDF only) *</Label>
                <div
                  className={`theme-dropzone mt-1 rounded-lg p-4 text-center transition-colors ${
                    paperDragActive
                      ? 'theme-dropzone--active'
                      : ''
                  }`}
                  onClick={() => document.getElementById('paperFile')?.click()}
                  onDragOver={(e) => handleDragOver(e, setPaperDragActive)}
                  onDragEnter={(e) => handleDragOver(e, setPaperDragActive)}
                  onDragLeave={(e) => handleDragLeave(e, setPaperDragActive)}
                  onDrop={(e) => handleDropFile(e, setPaperFile, setPaperDragActive, 'Paper file')}
                >
                  <input
                    type="file"
                    accept=".pdf"
                    onChange={(e) => handleFileSelection(e.target.files?.[0] || null, setPaperFile, 'Paper file')}
                    className="hidden"
                    id="paperFile"
                  />
                  <label htmlFor="paperFile" className="cursor-pointer">
                    <FileText className="mx-auto mb-2 h-8 w-8 text-muted-foreground" />
                    <p className="theme-muted text-sm">
                      {paperFile ? paperFile.name : 'Click to upload paper'}
                    </p>
                    <p className="theme-muted mt-1 text-xs">Only `.pdf` files are accepted. We will also try to auto-suggest details from this file.</p>
                  </label>
                </div>
              </div>
              <div>
                <Label className="theme-form-label">Solution File (Optional PDF)</Label>
                <div
                  className={`theme-dropzone mt-1 rounded-lg p-4 text-center transition-colors ${
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
