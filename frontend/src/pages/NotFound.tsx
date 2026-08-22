import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import SeoMeta from '@/components/SeoMeta';
import { Compass, Home, Search } from 'lucide-react';

export default function NotFoundPage() {
  return (
    <div className="min-h-[70vh] px-4 py-16">
      <SeoMeta
        title="Page not found"
        description="The requested UR Academic Resource Hub page could not be found."
        canonicalPath="/404"
        robots="noindex,nofollow"
      />
      <div className="mx-auto flex max-w-2xl flex-col items-center text-center">
        <div className="theme-empty-icon mb-6 flex h-20 w-20 items-center justify-center rounded-full">
          <Compass className="theme-section-icon h-10 w-10" />
        </div>
        <p className="theme-link-accent mb-2 text-sm font-semibold uppercase tracking-[0.2em]">404</p>
        <h1 className="theme-title mb-4 text-3xl font-bold">Page not found</h1>
        <p className="theme-muted mb-8 max-w-lg">
          The page you were trying to open does not exist or may have been moved. You can head back home
          or continue browsing academic resources.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <Button asChild className="theme-accent-bg">
            <Link to="/">
              <Home className="mr-2 h-4 w-4" />
              Go Home
            </Link>
          </Button>
          <Button asChild variant="outline">
            <Link to="/resources">
              <Search className="mr-2 h-4 w-4" />
              Browse Resources
            </Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
