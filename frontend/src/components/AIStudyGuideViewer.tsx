import React, { useState, useEffect, useRef } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  Sparkles,
  Copy,
  Check,
  BookOpen,
  GraduationCap,
  Lightbulb,
  FileText,
  Send,
  RotateCcw,
  Brain,
  Calculator,
  AlertTriangle,
} from 'lucide-react';
import { toast } from '@/lib/messages';
import AcademicAiMark from './AcademicAiMark';
import { fetchStudyAIStatus, AIStatusResponse } from '@/lib/client';

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
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const loadingSteps = [
    'Scanning exam paper & syllabus context...',
    'Analyzing curriculum competencies & questions...',
    'Synthesizing step-by-step revision strategy...',
    'Formatting comprehensive academic study guide...',
  ];

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
    const interval = setInterval(() => {
      setLoadingStep((prev) => (prev < loadingSteps.length - 1 ? prev + 1 : prev));
    }, 2000);
    return () => clearInterval(interval);
  }, [loading]);

  // Auto-scroll on new messages or loading state
  useEffect(() => {
    if (messages.length > 0 || loading) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages.length, loading]);

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

  const renderInlineStyles = (raw: string) => {
    const parts = raw.split(/(\*\*.*?\*\*|\$.*?\$|`.*?`)/g);
    return parts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return (
          <strong key={i} className="font-semibold text-foreground">
            {part.slice(2, -2)}
          </strong>
        );
      }
      if (part.startsWith('$') && part.endsWith('$') && part.length > 2) {
        return (
          <code
            key={i}
            className="rounded bg-primary/10 px-1.5 py-0.5 font-mono text-xs font-medium text-primary"
          >
            {part.slice(1, -1)}
          </code>
        );
      }
      if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
        return (
          <code
            key={i}
            className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-foreground"
          >
            {part.slice(1, -1)}
          </code>
        );
      }
      return part;
    });
  };

  const renderFormattedMarkdown = (text: string) => {
    const lines = text.split('\n');
    const elements: React.ReactNode[] = [];

    lines.forEach((line, index) => {
      const trimmed = line.trim();

      if (!trimmed) {
        elements.push(<div key={`empty-${index}`} className="h-2" />);
        return;
      }

      // H2 Headers
      if (trimmed.startsWith('## ')) {
        const title = trimmed.replace(/^##\s+/, '');
        elements.push(
          <div
            key={`h2-${index}`}
            className="mt-5 mb-2.5 pb-1.5 border-b border-border/60 flex items-center gap-2"
          >
            <span className="h-2 w-2 rounded-full bg-primary" />
            <h3 className="text-base font-bold text-foreground tracking-tight">
              {title}
            </h3>
          </div>
        );
        return;
      }

      // H3 Headers
      if (trimmed.startsWith('### ')) {
        const title = trimmed.replace(/^###\s+/, '');
        elements.push(
          <h4
            key={`h3-${index}`}
            className="mt-3.5 mb-1.5 text-sm font-semibold text-primary flex items-center gap-1.5"
          >
            <Lightbulb className="h-3.5 w-3.5 text-primary/80 shrink-0" />
            <span>{title}</span>
          </h4>
        );
        return;
      }

      // Blockquotes (> text)
      if (trimmed.startsWith('> ')) {
        elements.push(
          <div
            key={`quote-${index}`}
            className="my-2 border-l-2 border-primary/60 bg-primary/5 pl-3 py-1.5 text-xs text-muted-foreground rounded-r-md italic"
          >
            {renderInlineStyles(trimmed.slice(2))}
          </div>
        );
        return;
      }

      // Bullet points
      if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
        const rawContent = trimmed.substring(2);
        elements.push(
          <div
            key={`bullet-${index}`}
            className="flex items-start gap-2.5 my-1.5 pl-1.5 text-sm leading-relaxed"
          >
            <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary/70 shrink-0" />
            <div className="flex-1 text-muted-foreground">
              {renderInlineStyles(rawContent)}
            </div>
          </div>
        );
        return;
      }

      // Numbered items
      if (/^\d+\.\s+/.test(trimmed)) {
        const num = trimmed.match(/^(\d+)\.\s+/)?.[1] || '1';
        const rawContent = trimmed.replace(/^\d+\.\s+/, '');
        elements.push(
          <div
            key={`num-${index}`}
            className="flex items-start gap-2.5 my-2 pl-1.5 text-sm leading-relaxed"
          >
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-bold text-primary">
              {num}
            </span>
            <div className="flex-1 pt-0.5 text-muted-foreground">
              {renderInlineStyles(rawContent)}
            </div>
          </div>
        );
        return;
      }

      // Default paragraph
      elements.push(
        <p key={`p-${index}`} className="my-1.5 text-sm leading-relaxed text-muted-foreground">
          {renderInlineStyles(trimmed)}
        </p>
      );
    });

    return elements;
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
            <p className="text-[11px] text-muted-foreground">
              Instant revision guides, question breakdowns, and step-by-step exam solutions
            </p>
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
              <span>AI Assistant Active</span>
            </Badge>
          ) : (
            <Badge
              variant="outline"
              className="gap-1.5 py-1 px-2.5 text-[11px] font-medium border-border/70 bg-card text-muted-foreground"
            >
              <span className="h-2 w-2 rounded-full bg-amber-500" />
              <span>Paper Study Mode</span>
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
          Study Presets:
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
      <div className="max-h-[560px] overflow-y-auto p-4 space-y-4 divide-y divide-border/30">
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
                Click any study preset above or type a specific question about exam problems, formulas, or derivations below.
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
            const isLocal = msg.model === 'local-study-guide' || !msg.model;

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
                      <div className="flex items-center gap-1.5 mb-1 opacity-80 text-[10px]">
                        <span>You</span>
                        <span>•</span>
                        <span>
                          {msg.action ? getActionBadgeLabel(msg.action) : 'Question'}
                        </span>
                      </div>
                      <p className="leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                    </div>
                  </div>
                ) : (
                  /* Assistant Message Card */
                  <div className="rounded-xl border border-border/60 bg-card/60 p-4 shadow-sm space-y-3">
                    {/* Header with Role, Assistant Badge & Copy Button */}
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/40 pb-2.5">
                      <div className="flex items-center gap-2">
                        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/15 text-primary">
                          <Sparkles className="h-4 w-4" />
                        </div>
                        <div>
                          <div className="flex items-center gap-1.5">
                            <span className="text-xs font-bold text-foreground">
                              UR Academic Tutor
                            </span>
                            {msg.action && (
                              <span className="text-[10px] text-muted-foreground font-medium">
                                • {getActionBadgeLabel(msg.action)}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-1.5">
                        <Badge
                          variant={isLocal ? 'outline' : 'success'}
                          className="text-[10px] tracking-tight px-2 py-0.5"
                        >
                          {isLocal ? (
                            <span className="flex items-center gap-1">
                              <BookOpen className="h-3 w-3" />
                              Paper Context
                            </span>
                          ) : (
                            <span className="flex items-center gap-1">
                              <Sparkles className="h-3 w-3 text-primary" />
                              AI Study Guide
                            </span>
                          )}
                        </Badge>

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

                    {/* Clean Paper-Context Note if fallback */}
                    {isLocal && (
                      <div className="rounded-lg border border-border/60 bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                        <p className="leading-relaxed text-[11px]">
                          💡 Generated from uploaded exam paper text, course curriculum syllabus, and community solutions.
                        </p>
                      </div>
                    )}

                    {/* Markdown Body */}
                    <div className="prose prose-sm dark:prose-invert max-w-none">
                      {renderFormattedMarkdown(msg.content)}
                    </div>

                    {/* Follow-up Question Chips */}
                    <div className="pt-3 border-t border-border/30 flex flex-wrap gap-1.5 items-center">
                      <span className="text-[10px] font-semibold text-muted-foreground mr-1">
                        Follow-up:
                      </span>
                      <button
                        type="button"
                        onClick={() => handleTriggerAction('formulas')}
                        className="rounded-full border border-border bg-background/90 px-2.5 py-0.5 text-[11px] text-muted-foreground hover:border-primary hover:text-primary transition"
                      >
                        📐 Show formulas & theorems
                      </button>
                      <button
                        type="button"
                        onClick={() => handleTriggerAction('quiz')}
                        className="rounded-full border border-border bg-background/90 px-2.5 py-0.5 text-[11px] text-muted-foreground hover:border-primary hover:text-primary transition"
                      >
                        ❓ Generate 3 quiz questions
                      </button>
                      <button
                        type="button"
                        onClick={() => handleTriggerAction('pitfalls')}
                        className="rounded-full border border-border bg-background/90 px-2.5 py-0.5 text-[11px] text-muted-foreground hover:border-primary hover:text-primary transition"
                      >
                        ⚠️ Common exam traps
                      </button>
                    </div>
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
                  {loadingSteps[loadingStep]}
                </p>
                <p className="text-[11px] text-muted-foreground">
                  Analyzing document text & synthesizing revision notes...
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

        <div ref={messagesEndRef} />
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
            placeholder="Ask anything about this exam paper, specific questions, or derivations..."
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
