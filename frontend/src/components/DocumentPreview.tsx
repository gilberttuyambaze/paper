import { useEffect, useState } from 'react';
import { FileText } from 'lucide-react';
import ResourceLoadingAnimation from '@/components/ResourceLoadingAnimation';

type DocumentPreviewProps = {
  src?: string | null;
  title: string;
  minHeightClassName?: string;
  zoom?: number;
  onOpen?: () => void;
  unavailableMessage?: string;
  loadingTitle?: string;
  loadingDescription?: string;
  onRetry?: () => void;
};

const stages = ['Opening document', 'Preparing document', 'Fetching the file', 'Preparing reader', 'Almost ready'];

export default function DocumentPreview({ src, title, minHeightClassName = 'min-h-[520px]', zoom = 1, onOpen, unavailableMessage = 'This document preview is unavailable. Use the download button to view the full file.', loadingTitle = 'Preparing your book preview', loadingDescription = 'The book is opening securely. Larger files can take a little longer.', onRetry }: DocumentPreviewProps) {
  const [isLoading, setIsLoading] = useState(Boolean(src));
  const [failed, setFailed] = useState(false);
  const [progress, setProgress] = useState(8);

  useEffect(() => {
    setIsLoading(Boolean(src)); setFailed(false); setProgress(src ? 8 : 0);
    if (!src) return;
    const timer = window.setInterval(() => setProgress((value) => value >= 94 ? value : Math.min(94, value + (value < 55 ? 7 : value < 82 ? 3 : 1))), 550);
    return () => window.clearInterval(timer);
  }, [src]);

  const retry = () => { setFailed(false); setIsLoading(Boolean(src)); setProgress(8); onRetry?.(); };

  if (!src) return <div className={`theme-document-unavailable flex ${minHeightClassName} flex-col items-center justify-center gap-3 rounded-xl border border-dashed p-6 text-center`} role="status"><img src="/assets/icons/document-unavailable.svg" alt="" aria-hidden="true" className="h-14 w-14" /><p className="theme-muted max-w-md text-sm">{unavailableMessage}</p>{onOpen && <button type="button" onClick={onOpen} className="theme-link-accent text-sm font-semibold underline underline-offset-4">Try opening the document</button>}</div>;

  return <div className={`relative overflow-auto bg-background ${minHeightClassName}`} aria-label={`${title} document preview`} aria-busy={isLoading}>
    {(isLoading || failed) && <div className="document-preview-loading absolute inset-0 z-10 flex items-center justify-center bg-background/95 p-6" role="status" aria-live="polite">
      {failed ? <div className="max-w-sm text-center"><FileText className="mx-auto mb-4 h-10 w-10 text-muted-foreground" /><p className="theme-title font-semibold">We couldn’t open this document.</p><p className="theme-muted mt-2 text-sm">Its metadata is still available. Try loading the reader again.</p><button type="button" onClick={retry} className="theme-link-accent mt-4 text-sm font-semibold underline underline-offset-4">Retry</button></div> : <ResourceLoadingAnimation resource={title.toLowerCase().includes('paper') ? "Paper" : "Book"} progress={progress} stage={`${stages[Math.min(stages.length - 1, Math.floor(progress / 20))]}… ${loadingTitle || loadingDescription}`} />}
    </div>}
    <iframe src={src} title={title} className={`${minHeightClassName} w-full origin-top-left bg-background`} style={zoom === 1 ? undefined : { width: `${zoom * 100}%` }} onLoad={() => { setProgress(100); window.setTimeout(() => setIsLoading(false), 140); }} onError={() => { setIsLoading(false); setFailed(true); }} />
  </div>;
}
