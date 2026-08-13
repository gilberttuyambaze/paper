import React, { useEffect } from 'react';
import SeoMeta from '@/components/SeoMeta';

const LogoutCallbackPage: React.FC = () => {
  useEffect(() => {
    // The OIDC provider has logged out the user and redirected here
    // We can redirect to the home page or show a logout success message
    setTimeout(() => {
      window.location.href = '/';
    }, 2000);
  }, []);

  return (
    <div className="theme-auth-page flex min-h-screen items-center justify-center">
      <SeoMeta
        title="Logout successful"
        description="Logout callback page for UR Academic Resource Hub."
        canonicalPath="/auth/logout-callback"
        robots="noindex,nofollow"
      />
      <div className="text-center">
        <div className="theme-soft-panel mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full text-success-foreground">
          <svg
            className="h-6 w-6"
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h2 className="theme-title mb-2 text-2xl font-bold">
          Logout Successful
        </h2>
        <p className="theme-muted mb-4">
          You have been successfully logged out.
        </p>
        <p className="theme-muted text-sm">Redirecting to home page...</p>
      </div>
    </div>
  );
};

export default LogoutCallbackPage;
