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
    <div className="overflow-auto bg-background" aria-label={`${title} document preview`}>
      <iframe
        src={src}
        title={title}
        className={`${minHeightClassName} w-full origin-top-left bg-background`}
        style={zoom === 1 ? undefined : { width: `${zoom * 100}%` }}
      />
    </div>
  );
}
