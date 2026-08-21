import { Suspense, lazy } from 'react';
import { Toaster } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Navigate, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import ScrollToTop from './components/ScrollToTop';
import ProtectedAdminRoute from './components/ProtectedAdminRoute';

const Index = lazy(() => import('./pages/Index'));
const SearchResults = lazy(() => import('./pages/SearchResults'));
const PaperDetails = lazy(() => import('./pages/PaperDetails'));
const Upload = lazy(() => import('./pages/Upload'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Profile = lazy(() => import('./pages/Profile'));
const PublicProfile = lazy(() => import('./pages/PublicProfile'));
const Admin = lazy(() => import('./pages/Admin'));
const Story = lazy(() => import('./pages/Story'));
const Terms = lazy(() => import('./pages/Terms'));
const Privacy = lazy(() => import('./pages/Privacy'));
const AuthCallback = lazy(() => import('./pages/AuthCallback'));
const AuthError = lazy(() => import('./pages/AuthError'));
const LogoutCallbackPage = lazy(() => import('./pages/LogoutCallbackPage'));
const Login = lazy(() => import('./pages/Login'));
const Register = lazy(() => import('./pages/Register'));
const ForgotPassword = lazy(() => import('./pages/ForgotPassword'));
const ResetPassword = lazy(() => import('./pages/ResetPassword'));
const NotFoundPage = lazy(() => import('./pages/NotFound'));

const queryClient = new QueryClient();

function RouteFallback() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="theme-spinner h-8 w-8 animate-spin rounded-full border-b-2 border-current" />
    </div>
  );
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ScrollToTop />
        <Suspense fallback={<RouteFallback />}>
          <Routes>
            <Route path="/login" element={<Layout><Login /></Layout>} />
            <Route path="/register" element={<Layout><Register /></Layout>} />
            <Route path="/forgot-password" element={<Layout><ForgotPassword /></Layout>} />
            <Route path="/reset-password" element={<Layout><ResetPassword /></Layout>} />
            <Route path="/auth/callback" element={<AuthCallback />} />
            <Route path="/auth/error" element={<AuthError />} />
            <Route path="/auth/logout-callback" element={<LogoutCallbackPage />} />
            <Route path="/" element={<Layout><Index /></Layout>} />
            <Route path="/resources" element={<Layout><SearchResults /></Layout>} />
            <Route path="/search" element={<Navigate to="/resources" replace />} />
            <Route path="/past-papers" element={<Navigate to="/resources?type=paper" replace />} />
            <Route path="/study-resources" element={<Layout><Index /></Layout>} />
            <Route path="/story" element={<Layout><Story /></Layout>} />
            <Route path="/student-stories" element={<Layout><Story /></Layout>} />
            <Route path="/terms" element={<Layout><Terms /></Layout>} />
            <Route path="/privacy" element={<Layout><Privacy /></Layout>} />
            <Route path="/paper/:id" element={<Layout><PaperDetails /></Layout>} />
            <Route
              path="/upload"
              element={
                <ProtectedAdminRoute allowedRoles={['admin', 'cp']} title="upload">
                  <Layout><Upload /></Layout>
                </ProtectedAdminRoute>
              }
            />
            <Route path="/dashboard" element={<Layout><Dashboard /></Layout>} />
            <Route path="/books" element={<Navigate to="/resources?type=book" replace />} />
            <Route path="/profile" element={<Layout><Profile /></Layout>} />
            <Route path="/profile/:userId" element={<Layout><PublicProfile /></Layout>} />
            <Route
              path="/admin"
              element={
                <ProtectedAdminRoute allowedRoles={['admin', 'content_manager']} title="management">
                  <Layout>
                    <Admin />
                  </Layout>
                </ProtectedAdminRoute>
              }
            />
            <Route
              path="/content-manager"
              element={
                <ProtectedAdminRoute allowedRoles={['admin', 'content_manager']} title="management">
                  <Layout>
                    <Admin />
                  </Layout>
                </ProtectedAdminRoute>
              }
            />
            <Route path="*" element={<Layout><NotFoundPage /></Layout>} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
