import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { getStorageDownloadUrl } from '@/lib/client';

type AvatarFallbackProps = {
  name?: string | null;
  imageUrl?: string | null;
  profilePictureKey?: string | null;
  /** Use only where displaying this profile image is authorized. */
  imageAlt?: string;
  className?: string;
  textClassName?: string;
};

function initialsFor(name?: string | null) {
  const parts = (name || '')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2);
  return parts.length ? parts.map((part) => part[0]?.toUpperCase() || '').join('') : 'UR';
}

function patternFor(value?: string | null) {
  let hash = 0;
  for (const character of value || 'UR') hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return hash % 4;
}

export default function AvatarFallback({
  name,
  imageUrl,
  profilePictureKey,
  imageAlt,
  className,
  textClassName,
}: AvatarFallbackProps) {
  const [resolvedUrl, setResolvedUrl] = useState<string | null>(null);
  const [imageFailed, setImageFailed] = useState(false);
  const initials = initialsFor(name);
  const pattern = patternFor(name);

  useEffect(() => {
    setImageFailed(false);
    let cancelled = false;

    const source = profilePictureKey || imageUrl;
    if (!source) {
      setResolvedUrl(null);
      return;
    }

    if (/^(https?:\/\/|blob:|data:)/i.test(source)) {
      setResolvedUrl(source);
      return;
    }

    // It is a storage key - resolve download URL
    void getStorageDownloadUrl('profiles', source)
      .then((url) => {
        if (!cancelled) {
          setResolvedUrl(url);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setResolvedUrl(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [imageUrl, profilePictureKey]);

  if (resolvedUrl && !imageFailed) {
    return (
      <img
        src={resolvedUrl}
        alt={imageAlt || ''}
        onError={() => setImageFailed(true)}
        className={cn('h-full w-full object-cover', className)}
      />
    );
  }

  return (
    <span
      aria-label={imageAlt || `${name || 'User'} avatar`}
      className={cn('avatar-fallback flex h-full w-full items-center justify-center font-semibold', `avatar-fallback--${pattern}`, className)}
    >
      <span className={textClassName}>{initials}</span>
    </span>
  );
}
