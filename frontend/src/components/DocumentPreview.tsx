import { useEffect, useState } from 'react';
import { FileText } from 'lucide-react';
import DocumentLoadingProgress from './DocumentLoadingProgress';

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

export default function DocumentPreview({ src, title, minHeightClassName = 'min-h-[520px]', zoom = 1, onOpen, unavailableMessage = 'This document preview is unavailable. Use the download button to view the full file.', loadingTitle = 'Preparing your book preview', loadingDescription = 'The book is opening securely. Larger files can take a little longer.', onRetry }: DocumentPreviewProps) {
  const [isLoading, setIsLoading] = useState(Boolean(src));
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setIsLoading(Boolean(src)); setFailed(false);
    if (!src) return;
  }, [src]);

  const retry = () => { setFailed(false); setIsLoading(Boolean(src)); onRetry?.(); };

  if (!src) return <div className={`theme-document-unavailable flex ${minHeightClassName} flex-col items-center justify-center gap-3 rounded-xl border border-dashed p-6 text-center`} role="status"><img src="/assets/icons/document-unavailable.svg" alt="" aria-hidden="true" className="h-14 w-14" /><p className="theme-muted max-w-md text-sm">{unavailableMessage}</p>{onOpen && <button type="button" onClick={onOpen} className="theme-link-accent text-sm font-semibold underline underline-offset-4">Try opening the document</button>}</div>;

  return <div className={`relative overflow-auto bg-background ${minHeightClassName}`} aria-label={`${title} document preview`} aria-busy={isLoading}>
    {(isLoading || failed) && <div className="document-preview-loading absolute inset-0 z-10 flex items-center justify-center bg-background/95 p-6" role="status" aria-live="polite">
      {failed ? <div className="max-w-sm text-center"><FileText className="mx-auto mb-4 h-10 w-10 text-muted-foreground" /><p className="theme-title font-semibold">We couldn’t open this document.</p><button type="button" onClick={retry} className="theme-link-accent mt-4 text-sm font-semibold underline underline-offset-4">Retry</button></div> : <DocumentLoadingProgress resourceType={title.toLowerCase().includes('paper') ? "Paper" : "Book"} stage={loadingTitle || loadingDescription} />}
    </div>}
    <iframe src={src} title={title} className={`${minHeightClassName} w-full origin-top-left bg-background`} style={zoom === 1 ? undefined : { width: `${zoom * 100}%` }} onLoad={() => window.setTimeout(() => setIsLoading(false), 140)} onError={() => { setIsLoading(false); setFailed(true); }} />
  </div>;
}
