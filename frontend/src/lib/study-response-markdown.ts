/**
 * Normalization at the response-presentation boundary.
 *
 * The model-facing contract uses conventional LaTeX delimiters (`\\(...\\)`
 * and `\\[...\\]`), while remark-math consumes dollar delimiters. This narrow
 * adapter preserves fenced code verbatim and changes only complete, balanced
 * mathematical delimiters. It deliberately does not try to repair OCR, infer
 * equations, or rewrite ordinary prose.
 */
export function normalizeStudyResponseMarkdown(content: string): string {
  return content
    // Transport/UI labels are chrome, never part of an academic answer. Only
    // remove whole standalone lines so ordinary prose is left unchanged.
    .replace(/^\s*(?:svg(?:copy|ai study guide|optional ideas)?|svgcopy|svgai study guide)\s*$/gim, '')
    .split(/(```[\s\S]*?```)/g).map((segment, index) => {
    if (index % 2 === 1) return segment;
    return segment
      .replace(/\\\[([\s\S]*?)\\\]/g, (_match, expression: string) => `$$\n${expression.trim()}\n$$`)
      .replace(/\\\(([^\n]+?)\\\)/g, (_match, expression: string) => `$${expression.trim()}$`);
  }).join('');
}
