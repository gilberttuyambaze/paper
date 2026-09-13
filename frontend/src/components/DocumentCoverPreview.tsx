import React from 'react';
import { ShieldCheck, Sparkles, BookOpen, FileText, CheckCircle2 } from 'lucide-react';
import { getStorageDownloadUrl } from '../lib/client';

export interface DocumentCoverProps {
  title: string;
  courseCode?: string;
  courseName?: string;
  code?: string;
  year?: string | number;
  yearOfStudy?: string | null;
  semester?: string | null;
  paperType?: string;
  department?: string;
  coverUrl?: string | null;
  coverKey?: string | null;
  verificationStatus?: string;
  hasSolution?: boolean;
  isBook?: boolean;
  type?: 'paper' | 'book';
  size?: 'sm' | 'md' | 'lg' | 'hero';
  className?: string;
}

// Deterministic theme selection based on course code / title
function getCoverTheme(key: string) {
  let hash = 0;
  for (let i = 0; i < key.length; i++) {
    hash = (hash << 5) - hash + key.charCodeAt(i);
    hash |= 0;
  }
  const themes = [
    {
      id: 'dark-emerald',
      bgClass: 'bg-gradient-to-br from-[#062c24] via-[#064e3b] to-[#047857]',
      accentColor: '#10b981',
      pattern: 'circles',
      textClass: 'text-emerald-50',
      subtextClass: 'text-emerald-200/90',
      badgeClass: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
      watermarkColor: 'rgba(16, 185, 129, 0.15)',
    },
    {
      id: 'bright-emerald',
      bgClass: 'bg-gradient-to-br from-[#047857] via-[#059669] to-[#10b981]',
      accentColor: '#ffffff',
      pattern: 'overlapping-spheres',
      textClass: 'text-white',
      subtextClass: 'text-emerald-100',
      badgeClass: 'bg-white/25 text-white border-white/40',
      watermarkColor: 'rgba(255, 255, 255, 0.2)',
    },
    {
      id: 'clean-paper',
      bgClass: 'bg-gradient-to-br from-[#ffffff] via-[#f8fafc] to-[#e2e8f0]',
      accentColor: '#059669',
      pattern: 'grid-minimal',
      textClass: 'text-slate-900',
      subtextClass: 'text-slate-600',
      badgeClass: 'bg-emerald-600 text-white border-emerald-700',
      watermarkColor: 'rgba(5, 150, 105, 0.08)',
    },
    {
      id: 'obsidian-glow',
      bgClass: 'bg-gradient-to-br from-[#090d16] via-[#111827] to-[#1f293d]',
      accentColor: '#34d399',
      pattern: 'concentric-rings',
      textClass: 'text-slate-100',
      subtextClass: 'text-slate-300',
      badgeClass: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
      watermarkColor: 'rgba(52, 211, 153, 0.18)',
    },
    {
      id: 'sapphire-depth',
      bgClass: 'bg-gradient-to-br from-[#0a192f] via-[#1e3a8a] to-[#2563eb]',
      accentColor: '#60a5fa',
      pattern: 'geometric-arcs',
      textClass: 'text-white',
      subtextClass: 'text-blue-200',
      badgeClass: 'bg-blue-500/30 text-blue-200 border-blue-400/50',
      watermarkColor: 'rgba(96, 165, 250, 0.18)',
    },
    {
      id: 'regal-violet',
      bgClass: 'bg-gradient-to-br from-[#1e1035] via-[#4c1d95] to-[#7c3aed]',
      accentColor: '#c084fc',
      pattern: 'overlapping-spheres',
      textClass: 'text-white',
      subtextClass: 'text-purple-200',
      badgeClass: 'bg-purple-500/30 text-purple-200 border-purple-400/50',
      watermarkColor: 'rgba(192, 132, 252, 0.18)',
    },
  ];
  return themes[Math.abs(hash) % themes.length];
}

export default function DocumentCoverPreview({
  title,
  courseCode,
  courseName,
  code,
  year,
  yearOfStudy,
  semester,
  paperType = 'Exam',
  department,
  coverUrl,
  coverKey,
  verificationStatus,
  hasSolution,
  isBook,
  type,
  size = 'md',
  className = '',
}: DocumentCoverProps) {
  const finalCode = courseCode || code;
  const finalIsBook = isBook || type === 'book';
  const seed = `${finalCode || ''}-${title}-${paperType}-${finalIsBook ? 'b' : 'p'}`;
  const theme = getCoverTheme(seed);

  const [resolvedCoverUrl, setResolvedCoverUrl] = React.useState<string | null>(coverUrl || null);

  React.useEffect(() => {
    if (coverUrl) {
      setResolvedCoverUrl(coverUrl);
      return;
    }
    if (coverKey) {
      if (/^https?:\/\//i.test(coverKey)) {
        setResolvedCoverUrl(coverKey);
      } else {
        void getStorageDownloadUrl(finalIsBook ? 'books' : 'papers', coverKey)
          .then((url) => setResolvedCoverUrl(url))
          .catch(() => setResolvedCoverUrl(null));
      }
    }
  }, [coverUrl, coverKey, finalIsBook]);

  // Dimension scaling
  const sizeClasses = {
    sm: 'w-16 h-20 text-[8px] p-2',
    md: 'w-full h-24 sm:h-28 text-xs p-2.5 sm:p-3',
    lg: 'w-full aspect-[1/1.38] min-h-[200px] p-3.5 sm:p-4',
    hero: 'w-full aspect-[16/9] min-h-[145px] sm:min-h-[170px] p-3 sm:p-3.5',
  }[size];

  if (resolvedCoverUrl) {
    return (
      <div className={`relative overflow-hidden rounded-xl shadow-sm border border-border/40 group-hover:shadow-md transition-all duration-300 ${sizeClasses} ${className}`}>
        <img src={resolvedCoverUrl} alt={title} className="h-full w-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>
    );
  }

  const isLight = theme.id === 'clean-paper';
  const isCompact = size === 'md' || size === 'sm';

  return (
    <div
      className={`relative overflow-hidden rounded-xl sm:rounded-2xl shadow-sm group-hover:shadow-md transition-all duration-300 select-none flex flex-col justify-between ${theme.bgClass} ${sizeClasses} ${className}`}
      style={{
        boxShadow: isLight
          ? '0 4px 12px -2px rgba(0, 0, 0, 0.08), inset 3px 0 0 0 rgba(5, 150, 105, 0.8)'
          : '0 6px 16px -3px rgba(0, 0, 0, 0.35), inset 3px 0 0 0 rgba(255, 255, 255, 0.25)',
      }}
    >
      {/* 3D Spine effect on the left edge */}
      <div className="absolute left-0 top-0 bottom-0 w-2 bg-gradient-to-r from-black/35 via-black/10 to-transparent pointer-events-none" />

      {/* Decorative Background Motifs */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none opacity-80">
        {theme.pattern === 'circles' && (
          <svg className="absolute -right-8 -top-8 h-32 w-32" viewBox="0 0 100 100" fill="none">
            <circle cx="50" cy="50" r="46" stroke={theme.accentColor} strokeWidth="3" opacity="0.3" />
            <circle cx="50" cy="50" r="32" fill={theme.accentColor} opacity="0.2" />
            <circle cx="50" cy="50" r="14" fill={theme.accentColor} opacity="0.85" />
          </svg>
        )}
        {theme.pattern === 'concentric-rings' && (
          <svg className="absolute -right-6 -bottom-6 h-36 w-36" viewBox="0 0 100 100" fill="none">
            <circle cx="50" cy="50" r="45" stroke={theme.accentColor} strokeWidth="2.5" opacity="0.35" strokeDasharray="4 3" />
            <circle cx="50" cy="50" r="32" stroke={theme.accentColor} strokeWidth="3.5" opacity="0.7" />
            <circle cx="50" cy="50" r="16" fill={theme.accentColor} opacity="0.9" />
          </svg>
        )}
        {theme.pattern === 'overlapping-spheres' && (
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center justify-center pointer-events-none opacity-25">
            <div className="h-24 w-24 rounded-full border-2 border-white/60 -mr-8 backdrop-blur-sm" />
            <div className="h-20 w-20 rounded-full bg-white/30 backdrop-blur-sm" />
          </div>
        )}
        {theme.pattern === 'grid-minimal' && (
          <div
            className="absolute inset-0 opacity-15"
            style={{
              backgroundImage: 'radial-gradient(circle, #059669 1px, transparent 1px)',
              backgroundSize: '16px 16px',
            }}
          />
        )}
        {theme.pattern === 'geometric-arcs' && (
          <svg className="absolute -left-8 -bottom-8 h-36 w-36 opacity-30" viewBox="0 0 100 100" fill="none">
            <path d="M10 90 Q 90 90 90 10" stroke="#ffffff" strokeWidth="4" />
            <path d="M25 90 Q 90 90 90 25" stroke="#ffffff" strokeWidth="2" strokeDasharray="3 3" />
          </svg>
        )}
      </div>

      {/* Top Header: University Bar & Badge */}
      <div className="relative z-10 flex items-center justify-between gap-1 border-b pb-1 border-white/15">
        <div>
          <p className={`font-black tracking-[0.2em] uppercase text-[8px] sm:text-[9px] ${theme.subtextClass}`}>
            UR PAST PAPER
          </p>
        </div>

        <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[8px] sm:text-[9px] font-extrabold uppercase tracking-wide border shadow-sm ${theme.badgeClass}`}>
          {finalIsBook ? (
            <>
              <BookOpen className="h-2.5 w-2.5" />
              <span>BOOK</span>
            </>
          ) : (
            <>
              <FileText className="h-2.5 w-2.5" />
              <span>{paperType}</span>
            </>
          )}
        </span>
      </div>

      {/* Center Block: Code & Title snippet */}
      <div className="relative z-10 my-auto py-0.5 space-y-0.5">
        {finalCode && (
          <div className="inline-block">
            <span
              className={`inline-block font-black text-[10px] sm:text-xs tracking-wider uppercase px-1.5 py-0.5 rounded shadow-sm ${
                isLight ? 'bg-slate-900 text-white' : 'bg-white text-slate-950'
              }`}
            >
              {finalCode}
            </span>
          </div>
        )}

        <h4 className={`font-black leading-tight line-clamp-1 text-xs sm:text-[13px] ${theme.textClass}`}>
          {title}
        </h4>

        {!isCompact && courseName && courseName !== title && (
          <p className={`text-[11px] line-clamp-1 font-medium ${theme.subtextClass}`}>
            {courseName}
          </p>
        )}

        {!isCompact && (yearOfStudy || semester) && (
          <div className="flex flex-wrap items-center gap-1 pt-0.5">
            <span
              className={`inline-flex items-center gap-1 font-bold text-[9px] sm:text-[10px] px-1.5 py-0.5 rounded backdrop-blur-sm ${
                isLight ? 'bg-emerald-100/90 text-emerald-900 border border-emerald-300' : 'bg-white/15 text-white/95 border border-white/20'
              }`}
            >
              <Sparkles className="h-2.5 w-2.5 opacity-80" />
              {[yearOfStudy, semester].filter(Boolean).join(' · ')}
            </span>
          </div>
        )}
      </div>

      {/* Bottom Footer: Department/Verified, Year & Format */}
      <div className="relative z-10 pt-1 border-t border-white/15 flex items-center justify-between gap-1.5 text-[8px] sm:text-[9px]">
        <div className="flex items-center gap-1 font-semibold truncate">
          {verificationStatus === 'verified' ? (
            <span className="inline-flex items-center gap-1 text-emerald-400 font-bold">
              <CheckCircle2 className="h-2.5 w-2.5" />
              <span>Verified</span>
            </span>
          ) : (
            <span className={`truncate opacity-90 ${theme.subtextClass}`}>
              {department ? department.slice(0, 18) : 'University of Rwanda'}
            </span>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {year && (
            <span className={`px-1 py-0.5 rounded font-bold text-[8px] sm:text-[9px] ${isLight ? 'bg-slate-200 text-slate-800' : 'bg-black/40 text-white/90'}`}>
              {year}
            </span>
          )}
          <span className="font-extrabold px-1 py-0.5 rounded bg-red-600 text-white text-[7px] sm:text-[8px] tracking-wider shadow-sm">
            PDF
          </span>
        </div>
      </div>
    </div>
  );
}
