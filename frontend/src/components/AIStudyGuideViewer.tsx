import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  Sparkles,
  Copy,
  Check,
  BookOpen,
  GraduationCap,
  FileText,
  Send,
  RotateCcw,
  Brain,
  Calculator,
  AlertTriangle,
} from 'lucide-react';
import { toast } from '@/lib/messages';
import AcademicAiMark from './AcademicAiMark';
import { fetchStudyAIStatus, AIStatusResponse, AISourceCitation } from '@/lib/client';
import { normalizeStudyResponseMarkdown } from '@/lib/study-response-markdown';

export type AIStudyAction = 'explain' | 'summarize' | 'question' | 'quiz' | 'formulas' | 'pitfalls';

export interface StudyChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  action?: AIStudyAction;
  model?: string | null;
  provider?: string | null;
  fallbackReason?: string | null;
  duration_ms?: number | null;
  timestamp?: Date | string;
  sources?: AISourceCitation[];
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
}

export interface AIStudyGuideViewerProps {
  content?: string;
  model?: string | null;
  mode?: AIStudyAction | null;
  loading: boolean;
  fallbackReason?: string | null;
  messages?: StudyChatMessage[];
  isAuthenticated?: boolean;
  onRequireAuth?: () => void;
  onSendMessage?: (action: AIStudyAction, question?: string, preferredProvider?: string) => void;
  onClearMessages?: () => void;
  onQuickAction?: (promptText: string) => void;
}

interface LoadingStepInfo {
  steps: string[];
  subtitle: string;
}

function getDynamicLoadingInfo(action?: AIStudyAction | null, query?: string | null): LoadingStepInfo {
  const q = (query || '').trim().toLowerCase();

  // 1. Casual Greetings & Openers
  if (
    q &&
    (
      /^(hi|hello|hey|good\s+(morning|afternoon|evening|day)|greetings|howdy|what'?s\s+up|sup)\b/i.test(q) ||
      (q.length <= 12 && /^(hi|hello|hey|greetings)/i.test(q))
    )
  ) {
    return {
      steps: ['Connecting to AI assistant...', 'Thinking...'],
      subtitle: 'Ready to help you revise and explore this paper.',
    };
  }

  // 2. Question Collection / Extraction Intent
  if (
    q &&
    (
      q.includes('collect all questions') ||
      q.includes('list all questions') ||
      q.includes('find all questions') ||
      q.includes('show all questions') ||
      q.includes('all questions in') ||
      q.includes('extract questions') ||
      q.includes('get all questions') ||
      q.includes('all questions')
    )
  ) {
    return {
      steps: [
        'Reviewing the paper’s question inventory...',
        'Organizing sections, questions, and tasks...',
        'Preparing the complete collection...',
      ],
      subtitle: 'Using the paper’s saved academic evidence—no document reprocessing.',
    };
  }

  // 3. Solving specific sections or questions
  if (
    q &&
    (
      q.includes('section') ||
      q.includes('question') ||
      q.includes('solve') ||
      q.includes('answer') ||
      q.includes('calculate') ||
      /\bq\d+\b/i.test(q)
    )
  ) {
    return {
      steps: [
        'Locating relevant questions in paper context...',
        'Checking verified solutions & passages...',
        'Formulating clear step-by-step answer...',
      ],
      subtitle: 'Grounded in indexed paper text & verified solutions...',
    };
  }

  // 4. Action presets
  if (action === 'explain') {
    return {
      steps: [
        'Scanning exam paper & syllabus structure...',
        'Analyzing curriculum competencies...',
        'Synthesizing comprehensive revision guide...',
      ],
      subtitle: 'Compiling step-by-step revision strategy and core concepts...',
    };
  }

  if (action === 'summarize') {
    return {
      steps: [
        'Analyzing core paper topics & themes...',
        'Reviewing verified solutions & discussion notes...',
        'Synthesizing concise study brief...',
      ],
      subtitle: 'Extracting essential paper concepts and discussion points...',
    };
  }

  if (action === 'formulas') {
    return {
      steps: [
        'Searching for equations, laws, and definitions...',
        'Extracting mathematical & scientific relationships...',
        'Formatting formula reference sheet...',
      ],
      subtitle: 'Compiling key equations and theorems from paper...',
    };
  }

  if (action === 'pitfalls') {
    return {
      steps: [
        'Analyzing common student errors & tricky questions...',
        'Reviewing grading criteria & examiner traps...',
        'Compiling exam pitfall warnings...',
      ],
      subtitle: 'Identifying tricky questions and student mistakes to avoid...',
    };
  }

  if (action === 'quiz') {
    return {
      steps: [
        'Analyzing paper question types & difficulty...',
        'Drafting targeted practice questions...',
        'Preparing solutions & answer explanations...',
      ],
      subtitle: 'Generating practice quiz based on paper topics...',
    };
  }

  // Default fallback for any other question / prompt
  return {
    steps: [
      'Reviewing paper context & indexed passages...',
      'Analyzing your question...',
      'Formulating response...',
    ],
    subtitle: 'Searching indexed paper text and syllabus material...',
  };
}

export default function AIStudyGuideViewer({
  content,
  model,
  mode,
  loading,
  fallbackReason,
  messages = [],
  isAuthenticated = true,
  onRequireAuth,
  onSendMessage,
  onClearMessages,
  onQuickAction,
}: AIStudyGuideViewerProps) {
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [loadingStep, setLoadingStep] = useState(0);
  const [inputQuestion, setInputQuestion] = useState('');
  const [aiStatus, setAiStatus] = useState<AIStatusResponse | null>(null);
  const chatContainerRef = useRef<HTMLDivElement | null>(null);
  const prevUserMsgCountRef = useRef(0);

  const lastUserMessage = [...messages].reverse().find((m) => m.role === 'user');
  const activeAction = lastUserMessage?.action || mode;
  const activeQuery = lastUserMessage?.content;
  const loadingInfo = getDynamicLoadingInfo(activeAction, activeQuery);

  // Fetch live AI connection status on mount
  const checkStatus = async () => {
    try {
      const res = await fetchStudyAIStatus();
      setAiStatus(res);
    } catch {
      setAiStatus({
        enabled: true,
        is_connected: false,
        latency_ms: null,
        status: 'error',
        message: 'AI assistant is operating in offline/local study mode.',
      });
    }
  };

  useEffect(() => {
    void checkStatus();
  }, []);

  // Loading animation step cycle
  useEffect(() => {
    if (!loading) {
      setLoadingStep(0);
      return;
    }
    const maxSteps = loadingInfo.steps.length;
    const interval = setInterval(() => {
      setLoadingStep((prev) => (prev < maxSteps - 1 ? prev + 1 : prev));
    }, 1800);
    return () => clearInterval(interval);
  }, [loading, loadingInfo.steps.length]);

  // Auto-scroll ONLY inside the chat container when a new user message is sent.
  // Never scroll the outer window, and do not jump to the bottom when the assistant response arrives.
  useEffect(() => {
    const userMsgCount = messages.filter((m) => m.role === 'user').length;
    if (userMsgCount === 0) {
      prevUserMsgCountRef.current = 0;
      return;
    }
    if (userMsgCount > prevUserMsgCountRef.current) {
      prevUserMsgCountRef.current = userMsgCount;
      if (chatContainerRef.current) {
        chatContainerRef.current.scrollTo({
          top: chatContainerRef.current.scrollHeight,
          behavior: 'smooth',
        });
      }
    }
  }, [messages]);

  const handleCopy = async (textToCopy: string, id: string) => {
    if (!textToCopy) return;
    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopiedId(id);
      toast.success('Notes copied to clipboard!');
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      toast.error('Failed to copy text');
    }
  };

  const handleSendInput = () => {
    const trimmed = inputQuestion.trim();
    if (!trimmed || loading) return;
    if (!isAuthenticated && onRequireAuth) {
      onRequireAuth();
      return;
    }
    if (onSendMessage) {
      onSendMessage('question', trimmed);
    } else if (onQuickAction) {
      onQuickAction(trimmed);
    }
    setInputQuestion('');
  };

  const handleTriggerAction = (action: AIStudyAction) => {
    if (loading) return;
    if (!isAuthenticated && onRequireAuth) {
      onRequireAuth();
      return;
    }
    if (onSendMessage) {
      onSendMessage(action);
    } else if (onQuickAction) {
      if (action === 'explain') onQuickAction('Explain this paper and provide a study guide');
      else if (action === 'summarize') onQuickAction('Summarize the key themes and solutions for this paper');
      else if (action === 'formulas') onQuickAction('What are the key formulas and theorems for this exam?');
      else if (action === 'pitfalls') onQuickAction('What are the common exam pitfalls and student mistakes?');
      else if (action === 'quiz') onQuickAction('Generate a practice quiz with solutions for this paper');
    }
  };

  const displayMessages: StudyChatMessage[] =
    messages.length > 0
      ? messages
      : content
      ? [
          {
            id: 'legacy-single-content',
            role: 'assistant',
            content,
            model,
            action: mode || 'explain',
            fallbackReason,
            timestamp: new Date(),
          },
        ]
      : [];

  const getActionBadgeLabel = (act?: AIStudyAction) => {
    switch (act) {
      case 'explain':
        return '🎓 Study Guide';
      case 'summarize':
        return '📋 Discussion Brief';
      case 'formulas':
        return '📐 Formulas & Theorems';
      case 'pitfalls':
        return '⚠️ Common Pitfalls';
      case 'quiz':
        return '❓ Practice Quiz';
      case 'question':
      default:
        return '💬 Exam Q&A';
    }
  };

  const isAIConnected = aiStatus?.is_connected ?? true;

  return (
    <div className="theme-soft-panel rounded-2xl border border-border/70 shadow-md transition-all duration-200 overflow-hidden">
      {/* 1. Header Bar: Clean Academic Title, Status & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/50 bg-background/60 p-4">
        <div className="flex items-center gap-3">
          <div className="relative flex h-9 w-9 items-center justify-center rounded-xl bg-primary/15 text-primary shadow-inner">
            <Sparkles className="h-5 w-5 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h4 className="text-sm font-bold text-foreground">
                UR AI Study Assistant
              </h4>
              <span className="text-[10px] font-medium text-primary/90 bg-primary/10 px-2 py-0.5 rounded-full border border-primary/20">
                Academic Copilot
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground">Ask naturally about this paper. Answers stay grounded in its source material.</p>
          </div>
        </div>

        {/* Status indicator & Reset Button */}
        <div className="flex items-center gap-2">
          {isAIConnected ? (
            <Badge
              variant="outline"
              className="gap-1.5 py-1 px-2.5 text-[11px] font-medium border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
            >
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              <span>Study AI</span>
            </Badge>
          ) : (
            <Badge
              variant="outline"
              className="gap-1.5 py-1 px-2.5 text-[11px] font-medium border-border/70 bg-card text-muted-foreground"
            >
              <span className="h-2 w-2 rounded-full bg-amber-500" />
              <span>Paper context</span>
            </Badge>
          )}

          {/* Clear Conversation Button */}
          {displayMessages.length > 0 && onClearMessages && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 gap-1 text-xs text-muted-foreground hover:text-destructive hover:bg-destructive/10"
              onClick={onClearMessages}
              title="Reset study conversation"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              <span>Reset</span>
            </Button>
          )}
        </div>
      </div>

      {/* Unauthenticated Alert Banner */}
      {!isAuthenticated && (
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-primary/20 bg-primary/5 px-4 py-3 text-xs">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary">
              <Sparkles className="h-4 w-4" />
            </div>
            <div>
              <p className="font-semibold text-foreground">Sign in to access AI Study Assistant</p>
              <p className="text-[11px] text-muted-foreground">
                Log in or create a free account to generate step-by-step revision guides, practice quizzes, and formula sheets.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
            <Button
              type="button"
              size="sm"
              onClick={onRequireAuth}
              className="h-7 text-xs px-3 font-medium theme-accent-bg"
            >
              Sign In
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={onRequireAuth}
              className="h-7 text-xs px-3 font-medium border-border/80"
            >
              Create Account
            </Button>
          </div>
        </div>
      )}

      {/* 2. One-Click Quick Study Actions Ribbon */}
      <div className="flex flex-wrap items-center gap-1.5 border-b border-border/40 bg-card/40 p-2.5 overflow-x-auto">
        <span className="text-[11px] font-semibold text-muted-foreground mr-1 hidden sm:inline-flex items-center gap-1">
          <GraduationCap className="h-3.5 w-3.5" />
          Optional ideas:
        </span>
        <button
          type="button"
          onClick={() => handleTriggerAction('explain')}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border/80 bg-background px-2.5 py-1 text-xs font-medium text-foreground transition hover:border-primary hover:text-primary disabled:opacity-50"
        >
          <BookOpen className="h-3.5 w-3.5 text-primary" />
          <span>Full Study Guide</span>
        </button>
        <button
          type="button"
          onClick={() => handleTriggerAction('summarize')}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border/80 bg-background px-2.5 py-1 text-xs font-medium text-foreground transition hover:border-primary hover:text-primary disabled:opacity-50"
        >
          <FileText className="h-3.5 w-3.5 text-blue-500" />
          <span>Discussion Brief</span>
        </button>
        <button
          type="button"
          onClick={() => handleTriggerAction('formulas')}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border/80 bg-background px-2.5 py-1 text-xs font-medium text-foreground transition hover:border-primary hover:text-primary disabled:opacity-50"
        >
          <Calculator className="h-3.5 w-3.5 text-amber-500" />
          <span>Key Formulas</span>
        </button>
        <button
          type="button"
          onClick={() => handleTriggerAction('pitfalls')}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border/80 bg-background px-2.5 py-1 text-xs font-medium text-foreground transition hover:border-primary hover:text-primary disabled:opacity-50"
        >
          <AlertTriangle className="h-3.5 w-3.5 text-rose-500" />
          <span>Exam Pitfalls</span>
        </button>
        <button
          type="button"
          onClick={() => handleTriggerAction('quiz')}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border/80 bg-background px-2.5 py-1 text-xs font-medium text-foreground transition hover:border-primary hover:text-primary disabled:opacity-50"
        >
          <Brain className="h-3.5 w-3.5 text-purple-500" />
          <span>Practice Quiz</span>
        </button>
      </div>

      {/* 3. Conversational Message Stream */}
      <div
        ref={chatContainerRef}
        className="max-h-[560px] overflow-y-auto p-4 space-y-4 divide-y divide-border/30"
      >
        {displayMessages.length === 0 && !loading ? (
          <div className="py-10 text-center space-y-3">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary shadow-inner">
              <AcademicAiMark className="h-8 w-8" />
            </div>
            <div className="space-y-1.5 max-w-md mx-auto">
              <p className="text-sm font-bold text-foreground">
                Start Your Paper Revision Session
              </p>
              <p className="text-xs text-muted-foreground leading-relaxed">
                Ask anything about this paper: locate a topic, compare questions, learn a concept, create revision material, or follow up on an earlier answer.
              </p>
            </div>
            {/* Quick starter chips */}
            <div className="flex flex-wrap justify-center gap-2 pt-2 max-w-lg mx-auto">
              <button
                type="button"
                onClick={() => handleTriggerAction('explain')}
                className="text-xs rounded-full border border-border bg-background px-3 py-1 text-muted-foreground hover:border-primary hover:text-primary transition"
              >
                🎓 How should I study for this paper?
              </button>
              <button
                type="button"
                onClick={() => handleTriggerAction('formulas')}
                className="text-xs rounded-full border border-border bg-background px-3 py-1 text-muted-foreground hover:border-primary hover:text-primary transition"
              >
                📐 What formulas are required?
              </button>
              <button
                type="button"
                onClick={() => handleTriggerAction('quiz')}
                className="text-xs rounded-full border border-border bg-background px-3 py-1 text-muted-foreground hover:border-primary hover:text-primary transition"
              >
                ❓ Test me with 3 practice questions
              </button>
            </div>
          </div>
        ) : (
          displayMessages.map((msg, index) => {
            const isAssistant = msg.role === 'assistant';
            const isLocal = msg.model === 'local-study-guide';

            return (
              <div
                key={msg.id || `msg-${index}`}
                className={`pt-3 first:pt-0 ${
                  isAssistant ? 'space-y-2.5' : 'flex justify-end'
                }`}
              >
                {/* User Message Bubble */}
                {!isAssistant ? (
                  <div className="flex items-start gap-2.5 max-w-[85%]">
                    <div className="rounded-2xl rounded-tr-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground shadow-sm">
                      <p className="leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                    </div>
                  </div>
                ) : (
                  /* Assistant Message Card */
                  <div className="min-w-0 max-w-full overflow-hidden rounded-xl border border-border/60 bg-card/60 p-4 shadow-sm space-y-3">
                    {/* Header with Role, Assistant Badge & Copy Button */}
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/40 pb-2.5">
                      <div className="flex items-center gap-2">
                        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/15 text-primary">
                          <Sparkles className="h-4 w-4" />
                        </div>
                        <div>
                          <span className="text-xs font-bold text-foreground">Study AI</span>
                        </div>
                      </div>

                      <div className="flex items-center gap-1.5">
                        {isLocal && <Badge variant="outline" className="text-[10px] tracking-tight px-2 py-0.5">Paper context</Badge>}

                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="h-7 gap-1 px-2 text-xs font-medium text-muted-foreground hover:text-foreground"
                          onClick={() => handleCopy(msg.content, msg.id || `msg-${index}`)}
                        >
                          {copiedId === (msg.id || `msg-${index}`) ? (
                            <>
                              <Check className="h-3.5 w-3.5 text-emerald-500" />
                              <span className="text-[11px] text-emerald-600">Copied</span>
                            </>
                          ) : (
                            <>
                              <Copy className="h-3.5 w-3.5" />
                              <span className="text-[11px]">Copy</span>
                            </>
                          )}
                        </Button>
                      </div>
                    </div>

                    {/* Safe Markdown body: GFM tables and KaTeX are deliberate
                        response features, while raw model HTML remains inert. */}
                    <div className="study-ai-markdown min-w-0 max-w-full break-words prose prose-sm dark:prose-invert text-muted-foreground">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm, remarkMath]}
                        rehypePlugins={[rehypeKatex]}
                        components={{
                          h1: ({ children }) => <h2 className="mt-5 border-b border-border/60 pb-2 text-xl font-bold text-foreground first:mt-0">{children}</h2>,
                          h2: ({ children }) => <h3 className="mt-5 border-b border-border/60 pb-1.5 text-lg font-bold text-foreground">{children}</h3>,
                          h3: ({ children }) => <h4 className="mt-4 text-base font-semibold text-primary">{children}</h4>,
                          p: ({ children }) => <p className="my-2 leading-relaxed">{children}</p>,
                          ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5 marker:text-primary">{children}</ul>,
                          ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5 marker:font-semibold marker:text-primary">{children}</ol>,
                          blockquote: ({ children }) => <blockquote className="my-3 border-l-2 border-primary/60 bg-primary/5 py-1 pl-3 italic">{children}</blockquote>,
                          code: ({ className, children, ...props }) => className
                            ? <code className={className} {...props}>{children}</code>
                            : <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-foreground" {...props}>{children}</code>,
                          pre: ({ children }) => <pre className="max-w-full overflow-x-auto rounded-lg bg-muted p-3 text-xs text-foreground">{children}</pre>,
                          table: ({ children }) => <div className="study-ai-table-wrapper my-4 max-w-full overflow-x-auto rounded-lg border border-border"><table className="min-w-full border-collapse text-left text-sm">{children}</table></div>,
                          thead: ({ children }) => <thead className="bg-muted/70 text-foreground">{children}</thead>,
                          th: ({ children }) => <th className="border-b border-border px-3 py-2 font-semibold break-words">{children}</th>,
                          td: ({ children }) => <td className="border-b border-border/70 px-3 py-2 align-top break-words last:border-b-0">{children}</td>,
                          a: ({ children, href }) => <a className="text-primary underline underline-offset-2" href={href} target="_blank" rel="noreferrer">{children}</a>,
                        }}
                      >
                        {normalizeStudyResponseMarkdown(msg.content)}
                      </ReactMarkdown>
                    </div>

                    {/* Compact Structured Source Metadata */}
                    {msg.sources && msg.sources.length > 0 && (
                      <details className="mt-2 text-[11px] text-muted-foreground group">
                        <summary className="cursor-pointer font-medium hover:text-foreground inline-flex items-center gap-1">
                          <span>Sources</span>
                        </summary>
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {Array.from(
                            new Map(
                              msg.sources.map((s) => [
                                `${s.page_number}-${s.section_title || ''}-${s.question_number || ''}`,
                                s,
                              ])
                            ).values()
                          ).slice(0, 8).map((src, sIdx) => (
                            <span
                              key={sIdx}
                              className="inline-flex items-center gap-1 rounded bg-muted/50 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground border border-border/50"
                            >
                              Page {src.page_number}
                              {src.section_title ? ` • ${src.section_title}` : ''}
                              {src.question_number ? ` • Q${src.question_number}` : ''}
                            </span>
                          ))}
                        </div>
                      </details>
                    )}

                  </div>
                )}
              </div>
            );
          })
        )}

        {/* 4. Live Synthesis Loading State */}
        {loading && (
          <div className="rounded-xl border border-primary/30 bg-primary/5 p-4 space-y-3.5">
            <div className="flex items-center gap-3">
              <div className="relative flex h-8 w-8 items-center justify-center">
                <div className="h-8 w-8 rounded-full border-2 border-primary/20 border-t-primary animate-spin" />
                <div className="absolute inset-0 flex items-center justify-center">
                  <AcademicAiMark className="h-4 w-4 text-primary animate-pulse" />
                </div>
              </div>
              <div className="space-y-0.5">
                <p className="text-xs font-bold text-foreground animate-pulse">
                  {loadingInfo.steps[Math.min(loadingStep, loadingInfo.steps.length - 1)]}
                </p>
                <p className="text-[11px] text-muted-foreground">
                  {loadingInfo.subtitle}
                </p>
              </div>
            </div>

            {/* Shimmer skeleton lines */}
            <div className="space-y-2 pt-1 max-w-lg">
              <div className="h-3 bg-primary/15 rounded-full animate-pulse w-3/4" />
              <div className="h-2.5 bg-primary/10 rounded-full animate-pulse w-full" />
              <div className="h-2.5 bg-primary/10 rounded-full animate-pulse w-5/6" />
            </div>
          </div>
        )}
      </div>

      {/* 5. Interactive Chat Input Box */}
      <div className="border-t border-border/50 bg-background/70 p-3.5 space-y-2">
        <div className="relative">
          <Textarea
            value={inputQuestion}
            onChange={(e) => setInputQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSendInput();
              }
            }}
            placeholder="Ask naturally about this paper…"
            rows={2}
            className="theme-form-input pr-12 text-xs sm:text-sm resize-none"
            disabled={loading}
          />
          <Button
            type="button"
            size="sm"
            onClick={handleSendInput}
            disabled={loading || !inputQuestion.trim()}
            className="absolute right-2 bottom-2 h-7 w-7 p-0 rounded-lg theme-accent-bg"
            title="Send question (Enter)"
          >
            <Send className="h-3.5 w-3.5" />
          </Button>
        </div>
        <div className="flex items-center justify-between text-[11px] text-muted-foreground px-1">
          <span>Press <strong>Enter ↵</strong> to send, <strong>Shift+Enter</strong> for newline</span>
          <span className="text-[10px] text-muted-foreground/80">
            Powered by UR Academic Copilot
          </span>
        </div>
      </div>
    </div>
  );
}
