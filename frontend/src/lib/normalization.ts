export function normalizeText(value?: string | null): string | undefined {
  if (value == null) return undefined;
  return value.normalize('NFKC').replace(/[\r\n\t]+/g, ' ').replace(/\s+/g, ' ').trim() || undefined;
}

export function normalizeIdentifier(value?: string | null): string | undefined {
  const text = normalizeText(value);
  return text ? text.toLowerCase() : undefined;
}

export function normalizeSlug(value?: string | null): string | undefined {
  const text = normalizeText(value);
  if (!text) return undefined;
  const slug = text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  return slug || undefined;
}

export function normalizeEmail(value: string): string {
  return normalizeText(value)?.toLowerCase() || '';
}

export function normalizePhone(value?: string | null): string | undefined {
  const text = normalizeText(value);
  if (!text) return undefined;
  const digits = text.replace(/\D+/g, '');
  return digits.length >= 10 ? digits.slice(-10) : digits || undefined;
}

function validIsbn10(value: string): boolean {
  if (!/^\d{9}[\dX]$/i.test(value)) return false;
  return [...value].reduce((sum, char, index) => sum + (10 - index) * (char.toUpperCase() === 'X' ? 10 : Number(char)), 0) % 11 === 0;
}

function validIsbn13(value: string): boolean {
  if (!/^\d{13}$/.test(value)) return false;
  const checksum = [...value.slice(0, 12)].reduce((sum, char, index) => sum + Number(char) * (index % 2 ? 3 : 1), 0);
  return (10 - checksum % 10) % 10 === Number(value[12]);
}

export function normalizeIsbn(value?: string | null): string | undefined {
  const text = normalizeText(value);
  if (!text) return undefined;
  const candidates = text.match(/(?<!\d)(?:97[89][\d\s-]{9,16}|[\d][\d\s-]{8,14}[\dXx])(?!\d)/g) || [];
  for (const candidate of candidates) {
    const compact = candidate.replace(/[\s-]/g, '').toUpperCase();
    if (validIsbn13(compact) || validIsbn10(compact)) return compact;
  }
  const compact = text.replace(/[^0-9Xx]/g, '').toUpperCase();
  if (validIsbn13(compact) || validIsbn10(compact)) return compact;
  return undefined;
}

export function normalizeFilename(filename: string | null | undefined, fallback = 'document'): string {
  const normalized = (filename || '').normalize('NFKD').replace(/[^\x00-\x7F]/g, '').replace(/\\/g, '/').split('/').pop() || '';
  const match = normalized.match(/^(.*?)(\.[A-Za-z0-9]{1,12})?$/);
  const basename = (match?.[1] || '').replace(/[^A-Za-z0-9]+/g, '-').replace(/^-+|-+$/g, '').toLowerCase() || fallback;
  return `${basename.slice(0, 96)}${(match?.[2] || '').toLowerCase()}`;
}

export function buildStorageKey(bucket: string, namespace: string, filename: string, identity = 'upload'): string {
  const safeName = normalizeFilename(filename);
  const safeIdentity = identity.replace(/[^A-Za-z0-9_-]+/g, '-').slice(0, 32) || 'upload';
  const prefix = `${bucket.toLowerCase()}/${namespace.toLowerCase()}/${safeIdentity}-`;
  const extension = safeName.includes('.') ? safeName.slice(safeName.lastIndexOf('.')) : '';
  const basename = safeName.slice(0, safeName.length - extension.length);
  return `${prefix}${basename.slice(0, Math.max(1, 255 - prefix.length - extension.length))}${extension}`;
}

export function normalizeUnique<T>(values: Array<T | null | undefined>): T[] {
  const seen = new Set<string>();
  return values.filter((value): value is T => {
    const key = normalizeText(value == null ? undefined : String(value));
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function normalizeArrayIds<T extends string | number | null | undefined>(values: Array<T>): Array<string> {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    if (value == null) continue;
    const text = normalizeText(String(value));
    if (!text) continue;
    const normalized = text.replace(/[^A-Za-z0-9_-]+/g, '');
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    result.push(normalized);
  }
  return result;
}
