import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Shield, User, LogIn } from 'lucide-react';

interface ProtectedAdminRouteProps {
  children: React.ReactNode;
  requiredPermission: string;
  title?: string;
}

const ProtectedAdminRoute: React.FC<ProtectedAdminRouteProps> = ({
  children,
  title = 'management',
  requiredPermission,
}) => {
  const location = useLocation();
  const { user, loading, login } = useAuth();
  const isAllowed = !!user && user.permissions.includes(requiredPermission);

  // Loading state
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="text-center">
          <div className="theme-accent mx-auto mb-4 h-12 w-12 animate-spin rounded-full border-b-2 border-current"></div>
          <p className="theme-muted">Verifying permissions...</p>
        </div>
      </div>
    );
  }

  // If the user is not logged in, redirect to the login page
  if (!user) {
    return <Navigate to={`/login?returnTo=${encodeURIComponent(location.pathname)}`} replace />;
  }

  // If the user is not an admin, show an insufficient-permissions page
  if (!isAllowed) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <Card className="theme-panel w-full max-w-md">
          <CardHeader className="text-center">
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
              <Shield className="h-8 w-8 text-destructive" />
            </div>
            <CardTitle className="theme-title text-xl">
              Insufficient Permissions
            </CardTitle>
          </CardHeader>
          <CardContent className="text-center space-y-4">
            <div className="theme-muted">
              <p className="mb-2">
                The account you are using does not have the right access for the {title} area.
              </p>
              <div className="theme-panel-muted mb-4 rounded-lg p-3">
                <div className="flex items-center justify-center space-x-2 text-sm">
                  <User className="theme-muted h-4 w-4" />
                  <span className="text-foreground">
                    Current account: {user.email}
                  </span>
                </div>
                <div className="theme-muted mt-1 text-xs">
                  Role: {user.role}
                </div>
              </div>
              <p className="text-sm">
                This area requires the {requiredPermission} permission.
              </p>
            </div>

            <div className="space-y-3">
              <Button onClick={login} className="w-full" variant="outline">
                <LogIn className="h-4 w-4 mr-2" />
                Switch account
              </Button>

              <Button
                onClick={() => window.history.back()}
                className="w-full"
                variant="ghost"
              >
                Go back
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // If the user is allowed, render the child components
  return <>{children}</>;
};

export default ProtectedAdminRoute;
