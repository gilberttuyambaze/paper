import { LockKeyhole } from 'lucide-react';
import { motion, useReducedMotion } from 'framer-motion';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Navigate, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { getAPIBaseURL } from '@/lib/config';

const bookMessages = ['Learn', 'Explore', 'Achieve', 'Grow', 'Focus', 'Progress', 'Discover', 'Create'];
const bookStyles = ['book-style-warm', 'book-style-cool', 'book-style-green', 'book-style-ink'];

function createFloatingBooks() {
  const count = 7 + Math.floor(Math.random() * 5);
  return Array.from({ length: count }, (_, index) => ({
    id: `${index}-${Math.random()}`,
    message: bookMessages[Math.floor(Math.random() * bookMessages.length)],
    style: bookStyles[Math.floor(Math.random() * bookStyles.length)],
    path: Array.from({ length: 5 }, () => ({
      left: 2 + Math.random() * 91,
      top: 5 + Math.random() * 88,
    })),
    size: 0.65 + Math.random() * 0.8,
    duration: 7 + Math.random() * 8,
    delay: -Math.random() * 8,
    pageDelay: -Math.random() * 3.6,
    angle: -18 + Math.random() * 36,
    returnScale: 0.65 + Math.random() * 0.75,
  }));
}

export default function MaintenancePage() {
  const navigate = useNavigate();
  const { user, hasPermission } = useAuth();
  const reducedMotion = useReducedMotion();
  const [floatingBooks] = useState(createFloatingBooks);
  const bypass = hasPermission('site.maintenance.bypass');
  const [message, setMessage] = useState('We are performing scheduled maintenance. Normal website content is unavailable while this work is in progress.');

  useEffect(() => {
    void fetch(`${getAPIBaseURL()}/health/site-access`).then((response) => response.json()).then((data) => {
      if (typeof data.maintenance_message === 'string' && data.maintenance_message.trim()) setMessage(data.maintenance_message);
    }).catch(() => undefined);
  }, []);

  if (bypass) return <NavigateToHome />;

  return <main className="maintenance-screen flex min-h-screen items-center justify-center bg-background px-6 text-center">
    <div className="maintenance-floating-books" aria-hidden="true">
      {floatingBooks.map((book) => <motion.span
        className={`maintenance-floating-book ${book.style}`}
        key={book.id}
        style={{ left: `${book.path[0].left}%`, top: `${book.path[0].top}%`, scale: book.size, rotate: `${book.angle}deg`, '--page-delay': `${book.pageDelay}s` } as React.CSSProperties}
        animate={reducedMotion ? undefined : { left: book.path.map((point) => `${point.left}%`), top: book.path.map((point) => `${point.top}%`), scale: [book.size, book.size * 1.08, 0.08, book.returnScale, book.size], opacity: [0.58, 0.58, 0, 0.5, 0.58], rotate: [book.angle, book.angle + 8, book.angle - 6, book.angle + 12, book.angle] }}
        transition={{ repeat: Infinity, duration: book.duration, delay: book.delay, ease: 'easeInOut' }}
      ><strong>{book.message}</strong><span /><span /><b /><i /></motion.span>)}
    </div>
    <div className="relative z-10 max-w-lg">
      <motion.div
        className="maintenance-book-wrap mx-auto"
        aria-label="Book pages turning while the site is updated"
        role="img"
        animate={reducedMotion ? undefined : { y: [-3, 3, -3] }}
        transition={{ repeat: Infinity, duration: 2.8, ease: 'easeInOut' }}
      >
        <motion.div
          className="maintenance-book-halo"
          aria-hidden="true"
          animate={reducedMotion ? undefined : { scale: [1, 1.16, 1], opacity: [0.46, 0.2, 0.46] }}
          transition={{ repeat: Infinity, duration: 3.2, ease: 'easeInOut' }}
        />
        <div className="maintenance-book" aria-hidden="true">
          <div className="maintenance-book-cover maintenance-book-cover-left" />
          <div className="maintenance-book-cover maintenance-book-cover-right" />
          {[0, 1, 2, 3, 4].map((page) => <span className="maintenance-book-page" style={{ '--page-index': page } as React.CSSProperties} key={page} />)}
          <span className="maintenance-book-spine" />
        </div>
        <span className="maintenance-lock-badge"><LockKeyhole className="h-4 w-4" aria-hidden="true" /></span>
      </motion.div>
      <h1 className="theme-title mt-6 text-3xl font-bold">
        The site is temporarily unavailable
      </h1>
      <p className="theme-muted mt-4">
        {message}
      </p>
      {user ? 
      <p className="theme-muted mt-3 text-sm">
        Your account does not have access during this maintenance window.
      </p> : 
      <div className="mt-8 space-y-3">
          <Button onClick={() => navigate('/login?returnTo=%2Flocked')}>
            Authorized Staff Login</Button>
            <p className="theme-muted text-xs">
              Public access is temporarily paused. Authorized staff may log in below.
              </p>
      </div>
      }
    </div></main>;
}

function NavigateToHome() { return <Navigate to="/" replace />; }
