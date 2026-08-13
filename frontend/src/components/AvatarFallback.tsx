import { useState } from 'react';
import { cn } from '@/lib/utils';

type AvatarFallbackProps = {
  name?: string | null;
  imageUrl?: string | null;
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

export default function AvatarFallback({ name, imageUrl, imageAlt, className, textClassName }: AvatarFallbackProps) {
  const [imageFailed, setImageFailed] = useState(false);
  const initials = initialsFor(name);
  const pattern = patternFor(name);

  if (imageUrl && !imageFailed) {
    return (
      <img
        src={imageUrl}
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
