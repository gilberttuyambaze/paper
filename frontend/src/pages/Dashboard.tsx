import { useState, useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  fetchMyPapers,
  deleteMyPaper,
  fetchLeaderboard,
  fetchNotifications,
  fetchUserProfile,
  markAllNotificationsRead,
  markNotificationRead,
  Paper,
  UserProfile,
  NotificationItem,
} from '../lib/client';
import { authApi } from '../lib/auth';
import { useAuth } from '../contexts/AuthContext';
import OfflineDataBanner from '../components/OfflineDataBanner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from '@/components/ui/chart';
import {
  Upload,
  Download,
  FileText,
  CheckCircle,
  Users,
  Clock,
  Eye,
  Trash2,
  BarChart3,
  BookOpen,
  Trophy,
  Shield,
  Bell,
  CheckCheck,
} from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Pie, PieChart, XAxis } from 'recharts';
import { toast } from 'sonner';

function VerificationBadge({ status }: { status: string }) {
  if (status === 'verified') {
    return (
      <Badge className="theme-status-badge--verified hover:bg-inherit">
        <CheckCircle className="h-3 w-3 mr-1" />
        Verified
      </Badge>
    );
  }
  if (status === 'community') {
    return (
      <Badge className="theme-status-badge--community hover:bg-inherit">
        <Users className="h-3 w-3 mr-1" />
        Community
      </Badge>
    );
  }
  return (
    <Badge className="bg-muted text-muted-foreground hover:bg-muted">
      Unverified
    </Badge>
  );
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, loading: authLoading } = useAuth();
  const [papers, setPapers] = useState<Paper[]>([]);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [leaderboard, setLeaderboard] = useState<UserProfile[]>([]);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [showOfflineBanner, setShowOfflineBanner] = useState(false);
  const notificationsRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (user) loadMyPapers();
    else setLoading(false);
  }, [user]);

  useEffect(() => {
    if (location.hash !== '#notifications') return;

    window.requestAnimationFrame(() => {
      notificationsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }, [location.hash, notifications.length]);

  const loadMyPapers = async () => {
    try {
      setLoading(true);
      const [dataResult, profileResult, leaderboardResult, notificationResult] = await Promise.allSettled([
        fetchMyPapers(),
        fetchUserProfile(),
        fetchLeaderboard(),
        fetchNotifications(),
      ]);

      if (dataResult.status === 'fulfilled') {
        setPapers(dataResult.value.items);
        setShowOfflineBanner(dataResult.value.data_source === 'cache');
      } else {
        setPapers([]);
        setShowOfflineBanner(false);
      }

      setProfile(profileResult.status === 'fulfilled' ? profileResult.value : null);
      setLeaderboard(leaderboardResult.status === 'fulfilled' ? leaderboardResult.value : []);
      setNotifications(notificationResult.status === 'fulfilled' ? notificationResult.value : []);
    } catch (err) {
      console.error('Failed to load papers:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (paperId: number) => {
    try {
      await deleteMyPaper(paperId);
      setPapers((prev) => prev.filter((p) => p.id !== paperId));
      toast.success('Paper deleted');
    } catch {
      toast.error('Failed to delete paper');
    }
  };

  if (authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="theme-spinner h-8 w-8 animate-spin rounded-full border-b-2 border-current" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <h2 className="theme-title mb-4 text-2xl font-bold">Sign In Required</h2>
        <p className="theme-muted mb-6">
          Sign in to view your dashboard and manage your uploads.
        </p>
        <Button onClick={() => authApi.login('/dashboard')} className="theme-accent-bg">
          Sign In
        </Button>
      </div>
    );
  }

  const totalDownloads = papers.reduce((sum, p) => sum + (p.download_count || 0), 0);
  const verifiedCount = papers.filter((p) => p.verification_status === 'verified').length;
  const uploadTrend = [...papers]
    .sort((a, b) => new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime())
    .slice(-6)
    .map((paper) => ({
      title: paper.course_code,
      downloads: paper.download_count || 0,
    }));
  const verificationBreakdown = [
    { status: 'verified', papers: papers.filter((paper) => paper.verification_status === 'verified').length, fill: 'var(--color-verified)' },
    { status: 'community', papers: papers.filter((paper) => paper.verification_status === 'community').length, fill: 'var(--color-community)' },
    { status: 'unverified', papers: papers.filter((paper) => paper.verification_status === 'unverified').length, fill: 'var(--color-unverified)' },
  ];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {showOfflineBanner && (
        <OfflineDataBanner message="Your dashboard charts and upload list are currently using cached paper data." />
      )}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="theme-title text-3xl font-bold">My Dashboard</h1>
          <p className="theme-muted mt-1">{user?.email || 'Welcome back!'}</p>
        </div>
        <Button onClick={() => navigate('/upload')} className="theme-accent-bg">
          <Upload className="h-4 w-4 mr-2" />
          Upload Paper
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <Card className="theme-panel">
          <CardContent className="p-4 flex items-center gap-4">
            <div className="theme-soft-panel flex h-12 w-12 items-center justify-center rounded-lg text-info-foreground">
              <FileText className="h-6 w-6" />
            </div>
            <div>
              <p className="theme-title text-2xl font-bold">{papers.length}</p>
              <p className="theme-muted text-sm">My Uploads</p>
            </div>
          </CardContent>
        </Card>
        <Card className="theme-panel">
          <CardContent className="p-4 flex items-center gap-4">
            <div className="theme-soft-panel flex h-12 w-12 items-center justify-center rounded-lg text-success-foreground">
              <Download className="h-6 w-6" />
            </div>
            <div>
              <p className="theme-title text-2xl font-bold">{totalDownloads}</p>
              <p className="theme-muted text-sm">Total Downloads</p>
            </div>
          </CardContent>
        </Card>
        <Card className="theme-panel">
          <CardContent className="p-4 flex items-center gap-4">
            <div className="theme-accent-soft flex h-12 w-12 items-center justify-center rounded-lg">
              <CheckCircle className="theme-section-icon h-6 w-6" />
            </div>
            <div>
              <p className="theme-title text-2xl font-bold">{verifiedCount}</p>
              <p className="theme-muted text-sm">Verified</p>
            </div>
          </CardContent>
        </Card>
        <Card className="theme-panel">
          <CardContent className="p-4 flex items-center gap-4">
            <div className="theme-soft-panel flex h-12 w-12 items-center justify-center rounded-lg text-primary">
              <BarChart3 className="h-6 w-6" />
            </div>
            <div>
              <p className="theme-title text-2xl font-bold">
                {papers.length > 0 ? Math.round(totalDownloads / papers.length) : 0}
              </p>
              <p className="theme-muted text-sm">Avg Downloads</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="mb-8 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="theme-panel">
          <CardHeader>
            <CardTitle className="theme-title flex items-center gap-2">
              <Shield className="theme-section-icon h-5 w-5" />
              Contributor Status
            </CardTitle>
          </CardHeader>
          <CardContent className="theme-muted space-y-2 text-sm">
            <p>Role: <span className="font-semibold">{profile?.role || 'normal'}</span></p>
            {profile?.requested_role_status === 'pending' && (
              <p>
                Pending role request:
                <span className="font-semibold"> {profile.requested_role || 'special access'}</span>
              </p>
            )}
            {profile?.requested_role_status === 'approved' && profile?.requested_role && (
              <p>
                Recent role approval:
                <span className="font-semibold"> {profile.requested_role}</span>
              </p>
            )}
            <p>Institution: <span className="font-semibold">{profile?.institution_type === 'ur_student' ? 'University of Rwanda' : profile?.university_name || 'Not set'}</span></p>
            <p>UR verification: <span className="font-semibold">{profile?.ur_verification_status || 'not_requested'}</span></p>
            <p>Trust score: <span className="font-semibold">{profile?.trust_score || 0}</span></p>
            <p>Upload count: <span className="font-semibold">{profile?.upload_count || papers.length}</span></p>
            <p>Download count: <span className="font-semibold">{profile?.download_count || 0}</span></p>
            <div className="pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => navigate('/profile')}
              >
                View profile
              </Button>
            </div>
          </CardContent>
        </Card>
        <Card className="theme-panel">
          <CardHeader>
            <CardTitle className="theme-title flex items-center gap-2">
              <Trophy className="theme-section-icon h-5 w-5" />
              Leaderboard
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {leaderboard.slice(0, 5).map((entry, index) => (
              <div key={entry.id} className="theme-list-row flex items-center justify-between rounded-lg p-3 transition-colors">
                <div>
                  <p className="theme-title text-sm font-medium">
                    {index + 1}. {entry.display_name}
                  </p>
                </div>
                <Badge variant="secondary">{entry.trust_score || 0} pts</Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="mb-8 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card className="theme-panel">
          <CardHeader>
            <CardTitle className="theme-title">Download Performance</CardTitle>
          </CardHeader>
          <CardContent>
            <ChartContainer
              className="h-[260px] w-full"
              config={{
                downloads: { label: 'Downloads', color: 'hsl(var(--color-chart-1))' },
              }}
            >
              <BarChart data={uploadTrend}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="title" tickLine={false} axisLine={false} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar dataKey="downloads" radius={8} fill="var(--color-downloads)" />
              </BarChart>
            </ChartContainer>
          </CardContent>
        </Card>
        <Card className="theme-panel">
          <CardHeader>
            <CardTitle className="theme-title">Verification Mix</CardTitle>
          </CardHeader>
          <CardContent>
            <ChartContainer
              className="h-[260px] w-full"
              config={{
                verified: { label: 'Verified', color: 'hsl(var(--color-chart-2))' },
                community: { label: 'Community', color: 'hsl(var(--color-chart-3))' },
                unverified: { label: 'Unverified', color: 'hsl(var(--color-chart-4))' },
              }}
            >
              <PieChart>
                <ChartTooltip content={<ChartTooltipContent nameKey="status" />} />
                <Pie data={verificationBreakdown} dataKey="papers" nameKey="status" innerRadius={50} outerRadius={86} />
                <ChartLegend content={<ChartLegendContent nameKey="status" />} />
              </PieChart>
            </ChartContainer>
          </CardContent>
        </Card>
      </div>

      <Card
        id="notifications"
        ref={notificationsRef}
        className="theme-panel mb-8 scroll-mt-24"
      >
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="theme-title flex items-center gap-2">
            <Bell className="theme-section-icon h-5 w-5" />
            Notifications
          </CardTitle>
          <Button
            variant="outline"
            size="sm"
            onClick={async () => {
              await markAllNotificationsRead();
              setNotifications((prev) => prev.map((item) => ({ ...item, is_read: true })));
            }}
          >
            <CheckCheck className="mr-2 h-4 w-4" />
            Mark all read
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          {notifications.length === 0 ? (
            <p className="theme-muted text-sm">No notifications yet.</p>
          ) : (
            notifications.slice(0, 8).map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={async () => {
                  if (!item.is_read) {
                    await markNotificationRead(item.id);
                    setNotifications((prev) => prev.map((entry) => entry.id === item.id ? { ...entry, is_read: true } : entry));
                  }
                  if (item.related_entity === 'paper' && item.related_entity_id) {
                    navigate(`/paper/${item.related_entity_id}`);
                  }
                }}
                className={`w-full rounded-lg border p-3 text-left transition-colors ${
                  item.is_read
                    ? 'theme-list-row border-border'
                    : 'theme-accent-soft-border'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="theme-title text-sm font-medium">{item.title}</p>
                  {!item.is_read && <Badge>New</Badge>}
                </div>
                <p className="theme-muted mt-1 text-sm">{item.message}</p>
              </button>
            ))
          )}
        </CardContent>
      </Card>

      {/* My Papers */}
      <Card className="theme-panel">
        <CardHeader>
          <CardTitle className="theme-title flex items-center gap-2">
            <BookOpen className="theme-section-icon h-5 w-5" />
            My Uploaded Papers
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="theme-list-row animate-pulse flex items-center gap-4 rounded-lg p-4">
                  <div className="h-12 w-12 rounded bg-muted" />
                  <div className="flex-1 space-y-2">
                    <div className="h-4 w-3/4 rounded bg-muted" />
                    <div className="h-3 w-1/2 rounded bg-muted" />
                  </div>
                </div>
              ))}
            </div>
          ) : papers.length === 0 ? (
            <div className="text-center py-12">
              <FileText className="mx-auto mb-4 h-16 w-16 text-muted-foreground/45" />
              <h3 className="theme-title mb-2 text-lg font-semibold">No uploads yet</h3>
              <p className="theme-muted mb-4">Start contributing by uploading your first paper!</p>
              <Button onClick={() => navigate('/upload')} className="theme-accent-bg">
                <Upload className="h-4 w-4 mr-2" />
                Upload Paper
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              {papers.map((paper) => (
                <div
                  key={paper.id}
                  className="theme-list-row flex items-center gap-4 rounded-lg p-4 transition-colors"
                >
                  <div className="theme-accent-soft flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-lg">
                    <FileText className="theme-section-icon h-6 w-6" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h4 className="theme-title truncate font-medium">{paper.title}</h4>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      <span className="theme-muted text-xs">{paper.course_code}</span>
                      <span className="text-xs text-muted-foreground">·</span>
                      <span className="theme-muted text-xs">{paper.year}</span>
                      <span className="text-xs text-muted-foreground">·</span>
                      <span className="theme-muted text-xs">{paper.paper_type}</span>
                      <VerificationBadge status={paper.verification_status} />
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className="theme-muted flex items-center gap-1 text-xs">
                      <Download className="h-3.5 w-3.5" />
                      {paper.download_count || 0}
                    </span>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => navigate(`/paper/${paper.id}`)}
                      className="theme-ghost-brand-button h-8 w-8"
                    >
                      <Eye className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleDelete(paper.id)}
                      className="h-8 w-8 text-muted-foreground hover:text-error"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
