import { useEffect, useState } from 'react';
import { FileText, LoaderCircle } from 'lucide-react';

type DocumentPreviewProps = {
  src?: string | null;
  title: string;
  minHeightClassName?: string;
  zoom?: number;
  onOpen?: () => void;
  unavailableMessage?: string;
};

export default function DocumentPreview({
  src,
  title,
  minHeightClassName = 'min-h-[520px]',
  zoom = 1,
  onOpen,
  unavailableMessage = 'This document preview is unavailable. Use the download button to view the full file.',
}: DocumentPreviewProps) {
  const [isLoading, setIsLoading] = useState(Boolean(src));

  useEffect(() => {
    setIsLoading(Boolean(src));
  }, [src]);

  if (!src) {
    return (
      <div className="theme-document-unavailable flex flex-col items-center gap-3 rounded-xl border border-dashed p-6 text-center">
        <img src="/assets/icons/document-unavailable.svg" alt="" aria-hidden="true" className="h-14 w-14" />
        <p className="theme-muted max-w-md text-sm">{unavailableMessage}</p>
        {onOpen && <button type="button" onClick={onOpen} className="theme-link-accent text-sm font-semibold underline underline-offset-4">Try opening the document</button>}
      </div>
    );
  }

  return (
    <div className="relative overflow-auto bg-background" aria-label={`${title} document preview`} aria-busy={isLoading}>
      {isLoading && (
        <div className="document-preview-loading absolute inset-0 z-10 flex min-h-[inherit] items-center justify-center bg-background/95 p-6">
          <div className="max-w-sm text-center">
            <div className="document-preview-loader mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl">
              <FileText className="h-7 w-7" aria-hidden="true" />
              <LoaderCircle className="document-preview-spinner absolute h-11 w-11" aria-hidden="true" />
            </div>
            <p className="theme-title font-semibold">Preparing your paper preview</p>
            <p className="theme-muted mt-2 text-sm">The document is opening securely. This may take a moment for larger PDFs.</p>
          </div>
        </div>
      )}
      <iframe
        src={src}
        title={title}
        className={`${minHeightClassName} w-full origin-top-left bg-background`}
        style={zoom === 1 ? undefined : { width: `${zoom * 100}%` }}
        onLoad={() => setIsLoading(false)}
      />
    </div>
  );
}
