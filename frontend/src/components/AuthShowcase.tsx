import { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import BrandMark from '@/components/BrandMark';
import {
  BookOpen,
  Clock3,
  Landmark,
  ShieldCheck,
  Sparkles,
  UploadCloud,
} from 'lucide-react';

type AuthSlide = {
  title: string;
  description: string;
  image: string;
  accent: string;
  chips: string[];
};

const SLIDES: AuthSlide[] = [
  {
    title: 'Study smarter with trusted past papers',
    description:
      'Browse organized papers, verified uploads, and discussion threads that help you revise with confidence.',
    image: '/assets/illustrations/study-hero.svg',
    accent: 'from-primary via-warning to-secondary',
    chips: ['Verified papers', 'Fast search', 'Course-based'],
  },
  {
  title: 'Your university resources, connected',
  description:
    'A student-centered space for discovering past papers, sharing academic resources, and learning together across the University of Rwanda.',
  image: '/assets/illustrations/landing.jpg',
  accent: 'from-primary via-info to-secondary',
  chips: ['University of Rwanda', 'Past papers', 'Student community'],
 },
  {
    title: 'Share resources with your class community',
    description:
      'Upload exams, CATs, assignments, and model solutions so your classmates can build on real course materials.',
    image: '/assets/illustrations/peer-collaboration.svg',
    accent: 'from-info via-primary to-secondary',
    chips: ['Uploads', 'Solutions', 'Collaboration'],
  },
  {
    title: 'Keep your academic history in one place',
    description:
      'Track your contributions, manage downloads, and return to the resources you need throughout the semester.',
    image: '/assets/illustrations/document-upload.svg',
    accent: 'from-success via-info to-secondary',
    chips: ['Dashboard', 'Contribution log', 'Anywhere access'],
  },
];

const ICONS = [BookOpen, UploadCloud, ShieldCheck, Landmark];

export default function AuthShowcase() {
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    const root = document.documentElement;
    const storedTheme = localStorage.getItem('ur-theme');
    const isDark =
      storedTheme != null ? storedTheme === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;

    root.classList.toggle('dark', isDark);

    return () => {
      const currentTheme = localStorage.getItem('ur-theme');
      const stillDark =
        currentTheme != null
          ? currentTheme === 'dark'
          : window.matchMedia('(prefers-color-scheme: dark)').matches;
      root.classList.toggle('dark', stillDark);
    };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setActiveIndex((current) => (current + 1) % SLIDES.length);
    }, 4200);

    return () => window.clearInterval(timer);
  }, []);

  const activeSlide = SLIDES[activeIndex];
  const ActiveIcon = ICONS[activeIndex] ?? BookOpen;

  return (
    <div className="theme-auth-card relative overflow-hidden rounded-[2rem] p-6 md:p-8">
      <div
        className={`absolute inset-x-0 top-0 h-40 bg-gradient-to-br ${activeSlide.accent} opacity-90 transition-all duration-700`}
      />
      <div className="theme-auth-glow absolute inset-0" />

      <div className="relative z-10">
        <div className="mb-5 flex items-center justify-between gap-3">
          <Badge className="theme-surface-card border-0 px-3 py-1 text-foreground hover:bg-inherit">
            <Sparkles className="mr-2 h-3.5 w-3.5" />
            Student Access
          </Badge>
          <div className="theme-muted flex items-center gap-2 text-xs font-medium">
            <Clock3 className="h-4 w-4" />
            Auto slides on
          </div>
        </div>

        <div className="mb-6 flex items-center gap-4">
          <div className="theme-accent-bg flex h-14 w-14 items-center justify-center rounded-2xl shadow-lg">
            <ActiveIcon className="h-7 w-7" />
          </div>
          <div>
            <p className="theme-muted text-xs font-semibold uppercase tracking-[0.28em]">UR Resource Hub</p>
            <h2 className="theme-title text-2xl font-bold md:text-3xl">{activeSlide.title}</h2>
          </div>
        </div>

        <p className="theme-muted max-w-xl text-sm leading-6 md:text-base">{activeSlide.description}</p>

        <div className="mt-5 flex flex-wrap gap-2">
          {activeSlide.chips.map((chip) => (
            <span
              key={chip}
              className="theme-surface-card rounded-full px-3 py-1 text-xs font-medium"
            >
              {chip}
            </span>
          ))}
        </div>

        <div className="theme-surface-card mt-8 overflow-hidden rounded-[1.5rem] p-4 shadow-lg">
          <div className="grid gap-4 md:grid-cols-[1.15fr_0.85fr] md:items-center">
            <img
              src={activeSlide.image}
              alt=""
              className="h-56 w-full rounded-[1.2rem] object-cover md:h-72"
            />

            <div className="theme-header space-y-4 rounded-[1.2rem] p-5">
              <div className="flex items-center gap-3">
                <BrandMark imageClassName="h-8 w-8" />
                <p className="text-sm font-semibold">Built for University of Rwanda students</p>
              </div>
              <p className="theme-hero-copy text-sm leading-6">
                Sign in once to unlock uploads, dashboards, moderation tools, and the discussion space around each
                paper.
              </p>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="theme-hero-feature rounded-2xl p-3">
                  <p className="text-xl font-semibold">24/7</p>
                  <p className="theme-hero-feature-copy">paper access</p>
                </div>
                <div className="theme-hero-feature rounded-2xl p-3">
                  <p className="text-xl font-semibold">1 place</p>
                  <p className="theme-hero-feature-copy">for your resources</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-5 flex items-center gap-2">
          {SLIDES.map((slide, index) => (
            <button
              key={slide.title}
              type="button"
              aria-label={`Show slide ${index + 1}`}
              onClick={() => setActiveIndex(index)}
              className={`h-2.5 rounded-full transition-all ${
                index === activeIndex ? 'theme-home-indicator--active w-10' : 'theme-home-indicator w-2.5'
              }`}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
