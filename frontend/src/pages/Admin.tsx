import { useEffect, useState, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  fetchAdminRoleRequests,
  fetchProgrammeCandidatesDetailed,
  fetchProgrammeCandidateSubmissions,
  verifyProgrammeCandidate,
  rejectProgrammeCandidateGroup,
  deleteAdminUser,
  fetchAdminOverview,
  fetchAdminUsers,
  fetchAllPapers,
  moderatePaper,
  reviewAdminRoleRequest,
  updateAdminReport,
  updateAdminUser,
  type AdminOverview,
  type Paper,
  type UserProfile,
  type ProgrammeCandidateItem,
} from '../lib/client';
import AvatarFallback from '../components/AvatarFallback';
import { resolvePublicUserProfiles } from '../lib/client';
import { authApi } from '../lib/auth';
import { useAuth } from '../contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import {
  AlertTriangle,
  Ban,
  CheckCircle,
  Clock,
  Download,
  Eye,
  EyeOff,
  FileText,
  Flag,
  Mail,
  RefreshCcw,
  Search,
  Shield,
  Trash2,
  UserCog,
  Users,
} from 'lucide-react';
import { toast } from 'sonner';

const ROLE_OPTIONS = [
  { value: 'normal', label: 'Community Student' },
  { value: 'verified_contributor', label: 'Verified Contributor' },
  { value: 'cp', label: 'Class Representative (CP)' },
  { value: 'lecturer', label: 'Lecturer' },
  { value: 'content_manager', label: 'Content Manager' },
  { value: 'admin', label: 'Admin' },
];

const STATUS_OPTIONS = ['active', 'suspended', 'banned'];
const UR_OPTIONS = ['not_requested', 'pending', 'verified', 'rejected'];
const INSTITUTION_OPTIONS = ['ur_student', 'other_university'];

type UserDraft = {
  email: string;
  display_name: string;
  role: string;
  trust_score: string;
  account_status: string;
  ur_verification_status: string;
  institution_type: string;
  university_name: string;
  ur_student_code: string;
  phone_number: string;
  college_name: string;
  department_name: string;
  year_of_study: string;
  bio: string;
  suspension_reason: string;
};

function formatDate(value?: string | null) {
  if (!value) return 'Not available';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? 'Not available' : parsed.toLocaleString();
}

function createDraft(profile: UserProfile): UserDraft {
  return {
    email: profile.email || '',
    display_name: profile.display_name || '',
    role: profile.role || 'normal',
    trust_score: String(profile.trust_score ?? 0),
    account_status: profile.account_status || 'active',
    ur_verification_status: profile.ur_verification_status || 'not_requested',
    institution_type: profile.institution_type || 'ur_student',
    university_name: profile.university_name || '',
    ur_student_code: profile.ur_student_code || '',
    phone_number: profile.phone_number || '',
    college_name: profile.college_name || '',
    department_name: profile.department_name || '',
    year_of_study: profile.year_of_study || '',
    bio: profile.bio || '',
    suspension_reason: profile.suspension_reason || '',
  };
}

function useDebounced<T>(value: T, delay = 250) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

function RoleBadge({ role }: { role: string }) {
  const styles =
    role === 'admin'
      ? 'bg-error-soft text-error-foreground'
      : role === 'content_manager'
      ? 'bg-info-soft text-info-foreground'
      : role === 'lecturer'
      ? 'bg-primary/15 text-primary'
      : role === 'cp'
      ? 'bg-warning-soft text-warning-foreground'
      : role === 'verified_contributor'
      ? 'bg-success-soft text-success-foreground'
      : 'bg-muted text-muted-foreground';

  return <Badge className={styles}>{role.split('_').join(' ')}</Badge>;
}

function StatusBadge({ status }: { status?: string | null }) {
  const value = status || 'active';
  const styles =
    value === 'banned'
      ? 'bg-error-soft text-error-foreground'
      : value === 'suspended'
      ? 'bg-warning-soft text-warning-foreground'
      : 'bg-success-soft text-success-foreground';

  return <Badge className={styles}>{value}</Badge>;
}

function RequestedRoleBadge({
  requestedRole,
  requestedRoleStatus,
}: {
  requestedRole?: string | null;
  requestedRoleStatus?: string | null;
}) {
  if (!requestedRole || !requestedRoleStatus || requestedRoleStatus === 'none') {
    return null;
  }

  const styles =
    requestedRoleStatus === 'approved'
      ? 'bg-success-soft text-success-foreground'
      : requestedRoleStatus === 'rejected'
      ? 'bg-error-soft text-error-foreground'
      : 'bg-warning-soft text-warning-foreground';

  return <Badge className={styles}>{`${requestedRole} request: ${requestedRoleStatus}`}</Badge>;
}

function PaperVerificationBadge({ status }: { status: string }) {
  if (status === 'verified') {
    return <Badge className="bg-success-soft text-success-foreground">verified</Badge>;
  }
  if (status === 'community') {
    return <Badge className="bg-warning-soft text-warning-foreground">community</Badge>;
  }
  return <Badge variant="secondary">unverified</Badge>;
}

export default function AdminPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, loading: authLoading } = useAuth();
  const [papers, setPapers] = useState<Paper[]>([]);
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [roleRequests, setRoleRequests] = useState<UserProfile[]>([]);
  const [programmeCandidates, setProgrammeCandidates] = useState<ProgrammeCandidateItem[]>([]);
  const [selectedCandidateSubmissions, setSelectedCandidateSubmissions] = useState<Array<any>>([]);
  const [selectedCandidateName, setSelectedCandidateName] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [paperSearch, setPaperSearch] = useState('');
  const [userSearch, setUserSearch] = useState('');
  const [selectedUser, setSelectedUser] = useState<UserProfile | null>(null);
  const [draft, setDraft] = useState<UserDraft | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const isContentManagerView = location.pathname === '/content-manager' || user?.role === 'content_manager';
  const canAssignAdmin = user?.role === 'admin';
  const roleOptions = canAssignAdmin ? ROLE_OPTIONS : ROLE_OPTIONS.filter((option) => option.value !== 'admin');

  const loadData = async () => {
    try {
      setLoading(true);
      const [paperData, overviewData, userData, roleRequestData] = await Promise.all([
        fetchAllPapers({ sort: '-created_at', limit: 200 }),
        fetchAdminOverview(),
        fetchAdminUsers(),
        fetchAdminRoleRequests(),
      ]);
      setPapers(paperData.items);
      setOverview(overviewData);
      setUsers(userData);
      setRoleRequests(roleRequestData);
    } catch (error) {
      console.error('Failed to load management data:', error);
      toast.error('Failed to load management dashboard');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (user) {
      void loadData();
    }
  }, [user]);

  const debouncedUserSearch = useDebounced(userSearch, 250);
  const debouncedPaperSearch = useDebounced(paperSearch, 250);

  const filteredUsers = useMemo(() => {
    if (!debouncedUserSearch) return users;
    const q = debouncedUserSearch.toLowerCase();
    return users.filter((profile) =>
      profile.display_name.toLowerCase().includes(q) ||
      (profile.email || '').toLowerCase().includes(q) ||
      profile.role.toLowerCase().includes(q) ||
      (profile.university_name || '').toLowerCase().includes(q) ||
      (profile.ur_student_code || '').toLowerCase().includes(q)
    );
  }, [users, debouncedUserSearch]);

  const filteredRoleRequests = useMemo(() => {
    if (!debouncedUserSearch) return roleRequests;
    const q = debouncedUserSearch.toLowerCase();
    return roleRequests.filter((profile) =>
      profile.display_name.toLowerCase().includes(q) ||
      (profile.email || '').toLowerCase().includes(q) ||
      (profile.requested_role || '').toLowerCase().includes(q) ||
      (profile.university_name || '').toLowerCase().includes(q) ||
      (profile.ur_student_code || '').toLowerCase().includes(q)
    );
  }, [roleRequests, debouncedUserSearch]);

  const filteredPapers = useMemo(() => {
    if (!debouncedPaperSearch) return papers;
    const q = debouncedPaperSearch.toLowerCase();
    return papers.filter((paper) =>
      paper.title.toLowerCase().includes(q) ||
      paper.course_code.toLowerCase().includes(q) ||
      paper.course_name.toLowerCase().includes(q) ||
      (paper.lecturer || '').toLowerCase().includes(q)
    );
  }, [papers, debouncedPaperSearch]);

  const pendingPapers = useMemo(() => filteredPapers.filter((paper) => paper.verification_status === 'unverified'), [filteredPapers]);
  const reportedPapers = useMemo(() => filteredPapers.filter((paper) => (paper.report_count || 0) > 0), [filteredPapers]);
  const hiddenPapers = useMemo(() => filteredPapers.filter((paper) => paper.is_hidden), [filteredPapers]);
  const totalDownloads = useMemo(() => papers.reduce((sum, paper) => sum + (paper.download_count || 0), 0), [papers]);
  // Pagination state to avoid rendering huge lists at once
  const [userPage, setUserPage] = useState(1);
  const USERS_PER_PAGE = 50;
  const userPageCount = Math.max(1, Math.ceil(filteredUsers.length / USERS_PER_PAGE));
  const paginatedUsers = useMemo(() => {
    const start = (userPage - 1) * USERS_PER_PAGE;
    return filteredUsers.slice(start, start + USERS_PER_PAGE);
  }, [filteredUsers, userPage]);

  useEffect(() => {
    if (userPage > userPageCount) setUserPage(1);
  }, [userPageCount]);

  const [roleRequestPage, setRoleRequestPage] = useState(1);
  const ROLE_REQUESTS_PER_PAGE = 50;
  const roleRequestPageCount = Math.max(1, Math.ceil(filteredRoleRequests.length / ROLE_REQUESTS_PER_PAGE));
  const paginatedRoleRequests = useMemo(() => {
    const start = (roleRequestPage - 1) * ROLE_REQUESTS_PER_PAGE;
    return filteredRoleRequests.slice(start, start + ROLE_REQUESTS_PER_PAGE);
  }, [filteredRoleRequests, roleRequestPage]);

  useEffect(() => {
    if (roleRequestPage > roleRequestPageCount) setRoleRequestPage(1);
  }, [roleRequestPageCount]);

  const [paperPage, setPaperPage] = useState(1);
  const PAPERS_PER_PAGE = 50;
  const paperPageCount = Math.max(1, Math.ceil(filteredPapers.length / PAPERS_PER_PAGE));
  const paginatedPapers = useMemo(() => {
    const start = (paperPage - 1) * PAPERS_PER_PAGE;
    return filteredPapers.slice(start, start + PAPERS_PER_PAGE);
  }, [filteredPapers, paperPage]);

  useEffect(() => {
    if (paperPage > paperPageCount) setPaperPage(1);
  }, [paperPageCount]);
  const [uploaderProfiles, setUploaderProfiles] = useState<Record<string, { profile?: any; imageUrl?: string | null }>>({});
  const selectedUserIsAdmin = selectedUser?.role === 'admin';
  const adminProtected = selectedUserIsAdmin && !canAssignAdmin;

  const handleSaveUser = async () => {
    if (!selectedUser || !draft) return;

    try {
      setSaving(true);
      const updated = await updateAdminUser(selectedUser.id, {
        email: draft.email,
        display_name: draft.display_name,
        role: draft.role,
        trust_score: Number(draft.trust_score || '0'),
        account_status: draft.account_status,
        ur_verification_status: draft.ur_verification_status,
        institution_type: draft.institution_type as 'ur_student' | 'other_university',
        university_name: draft.university_name || null,
        ur_student_code: draft.ur_student_code || null,
        phone_number: draft.phone_number || null,
        college_name: draft.college_name || null,
        department_name: draft.department_name || null,
        year_of_study: draft.year_of_study || null,
        bio: draft.bio || null,
        suspension_reason: draft.suspension_reason || '',
      });
      setUsers((current) => current.map((profile) => (profile.id === updated.id ? updated : profile)));
      setRoleRequests((current) => {
        const remaining = current.filter((profile) => profile.id !== updated.id);
        if (updated.requested_role_status === 'pending') {
          return [updated, ...remaining];
        }
        return remaining;
      });
      setSelectedUser(updated);
      setDraft(createDraft(updated));
      toast.success('User updated successfully');
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || 'Failed to update user');
    } finally {
      setSaving(false);
    }
  };

  const visiblePaperIds = useMemo(() => Array.from(new Set(paginatedPapers.map((p) => p.user_id))).filter(Boolean), [paginatedPapers]);

  useEffect(() => {
    if (visiblePaperIds.length === 0) {
      setUploaderProfiles({});
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const resolved = await resolvePublicUserProfiles(visiblePaperIds);
        if (cancelled) return;
        const next: Record<string, { profile?: any; imageUrl?: string | null }> = {};
        for (const id of visiblePaperIds) {
          const r = resolved[id] || {};
          next[id] = { profile: r.profile || undefined, imageUrl: r.imageUrl ?? null };
        }
        setUploaderProfiles(next);
      } catch (e) {
        // ignore
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [visiblePaperIds]);

  const handleDeleteUser = async () => {
    if (!selectedUser) return;
    if (!window.confirm(`Delete ${selectedUser.display_name}'s account and related content?`)) {
      return;
    }

    try {
      setDeleting(true);
      await deleteAdminUser(selectedUser.id);
      setUsers((current) => current.filter((profile) => profile.id !== selectedUser.id));
      setDialogOpen(false);
      setSelectedUser(null);
      setDraft(null);
      toast.success('User deleted');
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || 'Failed to delete user');
    } finally {
      setDeleting(false);
    }
  };

  const handleVerifyPaper = async (paperId: number) => {
    try {
      const updated = await moderatePaper(paperId, { verification_status: 'verified' });
      setPapers((current) => current.map((paper) => (paper.id === updated.id ? updated : paper)));
      toast.success('Paper verified');
    } catch {
      toast.error('Failed to verify paper');
    }
  };

  const handleTogglePaperVisibility = async (paperId: number, isHidden: boolean) => {
    try {
      const updated = await moderatePaper(paperId, { is_hidden: !isHidden });
      setPapers((current) => current.map((paper) => (paper.id === updated.id ? updated : paper)));
      toast.success(isHidden ? 'Paper is visible again' : 'Paper hidden successfully');
    } catch {
      toast.error('Failed to update paper');
    }
  };

  const handleRoleRequestReview = async (profileId: number, action: 'approve' | 'reject') => {
    try {
      const updated = await reviewAdminRoleRequest(profileId, { action });
      setUsers((current) => current.map((profile) => (profile.id === updated.id ? updated : profile)));
      setRoleRequests((current) => current.filter((profile) => profile.id !== profileId));
      setOverview((current) =>
        current
          ? {
              ...current,
              stats: {
                ...current.stats,
                pending_role_requests: Math.max(0, (current.stats.pending_role_requests || 0) - 1),
              },
            }
          : current
      );
      if (selectedUser?.id === updated.id) {
        setSelectedUser(updated);
        setDraft(createDraft(updated));
      }
      toast.success(action === 'approve' ? 'Role request approved' : 'Role request rejected');
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || 'Failed to review role request');
    }
  };

  if (authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="theme-accent h-8 w-8 animate-spin rounded-full border-b-2 border-current" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 text-center">
        <Shield className="mx-auto mb-4 h-16 w-16 text-muted-foreground/40" />
        <h2 className="theme-title mb-4 text-2xl font-bold">Management Access Required</h2>
        <p className="theme-muted mb-6">Sign in to access the management dashboard.</p>
        <Button onClick={() => authApi.login('/admin')} className="theme-accent-bg">
          Sign In
        </Button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-3 flex items-center gap-3">
            <Shield className="theme-section-icon h-8 w-8" />
            <h1 className="theme-title text-3xl font-bold">
              {isContentManagerView ? 'Content Manager Dashboard' : 'Admin Dashboard'}
            </h1>
          </div>
          <p className="theme-muted max-w-2xl text-sm">
            Manage roles, review contributors, moderate reports, and keep the paper library clean and trusted.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button variant="outline" onClick={() => void loadData()}>
            <RefreshCcw className="mr-2 h-4 w-4" />
            Refresh data
          </Button>
          <Button onClick={() => navigate('/dashboard')} className="theme-accent-bg">
            Open dashboard
          </Button>
        </div>
      </div>

      <div className="mb-8 grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 items-stretch">
        <Card className="theme-panel h-[10vh] sm:h-auto">
          <CardContent className="p-4 text-center h-full flex flex-col justify-center">
            <Users className="theme-section-icon mx-auto mb-2 h-6 w-6" />
            <p className="theme-title text-2xl font-bold">{overview?.stats.total_users || users.length}</p>
            <p className="theme-muted text-xs">Users</p>
          </CardContent>
        </Card>
        <Card className="theme-panel h-[10vh] sm:h-auto">
          <CardContent className="p-4 text-center h-full flex flex-col justify-center">
            <FileText className="mx-auto mb-2 h-6 w-6 text-info" />
            <p className="theme-title text-2xl font-bold">{overview?.stats.total_papers || papers.length}</p>
            <p className="theme-muted text-xs">Papers</p>
          </CardContent>
        </Card>
        <Card className="theme-panel h-[10vh] sm:h-auto">
          <CardContent className="p-4 text-center h-full flex flex-col justify-center">
            <AlertTriangle className="mx-auto mb-2 h-6 w-6 text-warning" />
            <p className="theme-title text-2xl font-bold">{overview?.stats.pending_reports || 0}</p>
            <p className="theme-muted text-xs">Pending Reports</p>
          </CardContent>
        </Card>
        <Card className="theme-panel h-[10vh] sm:h-auto">
          <CardContent className="p-4 text-center h-full flex flex-col justify-center">
            <Download className="mx-auto mb-2 h-6 w-6 text-success" />
            <p className="theme-title text-2xl font-bold">{totalDownloads.toLocaleString()}</p>
            <p className="theme-muted text-xs">Downloads</p>
          </CardContent>
        </Card>
        <Card className="theme-panel h-[10vh] sm:h-auto">
          <CardContent className="p-4 text-center h-full flex flex-col justify-center">
            <Clock className="mx-auto mb-2 h-6 w-6 text-primary" />
            <p className="theme-title text-2xl font-bold">{overview?.stats.pending_role_requests || roleRequests.length}</p>
            <p className="theme-muted text-xs">Role Requests</p>
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="users" className="space-y-5">
        <TabsList className="bg-secondary rounded-lg p-2 h-auto w-full">
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 w-full items-stretch">
              <TabsTrigger value="users" className="w-full px-3 py-2 text-sm rounded-md flex items-center justify-center gap-2">Users ({filteredUsers.length})</TabsTrigger>
              <TabsTrigger value="role-requests" className="w-full px-3 py-2 text-sm rounded-md flex items-center justify-center gap-2">Role Requests ({overview?.stats.pending_role_requests || filteredRoleRequests.length})</TabsTrigger>
              <TabsTrigger value="reports" className="w-full px-3 py-2 text-sm rounded-md flex items-center justify-center gap-2">Reports ({overview?.recent_reports?.length || 0})</TabsTrigger>
              <TabsTrigger value="papers" className="w-full px-3 py-2 text-sm rounded-md flex items-center justify-center gap-2">Papers ({filteredPapers.length})</TabsTrigger>
              <TabsTrigger value="programme-candidates" className="w-full px-3 py-2 text-sm rounded-md flex items-center justify-center gap-2">Programme Discovery</TabsTrigger>
            </div>
          </TabsList>

        <TabsContent value="users">
          <Card className="theme-panel">
            <CardHeader>
              <CardTitle className="theme-title flex items-center gap-2">
                <UserCog className="theme-section-icon h-5 w-5" />
                User Management
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="relative">
                <Search className="theme-muted absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2" />
                <Input
                  value={userSearch}
                  onChange={(event) => setUserSearch(event.target.value)}
                  placeholder="Search by name, email, role, or UR code..."
                  className="pl-10"
                />
              </div>

              {loading ? (
                <div className="grid gap-4 md:grid-cols-2">
                  {[1, 2, 3, 4].map((item) => (
                    <div key={item} className="h-40 animate-pulse rounded-2xl bg-muted" />
                  ))}
                </div>
              ) : filteredUsers.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-border px-6 py-12 text-center text-sm text-muted-foreground">
                  No users match the current search.
                </div>
              ) : (
                <div className="space-y-2">
                  {paginatedUsers.map((profile) => (
                    <div key={profile.id} className="p-2 rounded border">
                      <div className="font-medium">{profile.display_name}</div>
                      <div className="text-xs text-muted-foreground">{profile.email || ''}</div>
                    </div>
                  ))}
                  <div className="mt-2 flex items-center justify-center gap-2">
                    <Button disabled={userPage <= 1} onClick={() => setUserPage((p) => Math.max(1, p - 1))}>{'<'}</Button>
                    <div className="text-sm">Page {userPage} / {userPageCount}</div>
                    <Button disabled={userPage >= userPageCount} onClick={() => setUserPage((p) => Math.min(userPageCount, p + 1))}>{'>'}</Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

          <Dialog open={detailsOpen} onOpenChange={(open) => setDetailsOpen(open)}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Submissions for {selectedCandidateName}</DialogTitle>
                <DialogDescription>Original submitted values (user identity hidden) and status.</DialogDescription>
              </DialogHeader>
              <div className="space-y-2">
                {selectedCandidateSubmissions.length === 0 ? (
                  <p className="theme-muted">No submissions found.</p>
                ) : (
                  selectedCandidateSubmissions.map((s) => (
                    <div key={s.id} className="theme-soft-panel p-2 rounded">
                      <p className="theme-title text-sm">{s.raw_programme_name}</p>
                      <p className="theme-muted text-xs">Normalized: {s.normalized_programme_name} · Status: {s.status} · Created: {s.created_at || 'n/a'}</p>
                    </div>
                  ))
                )}
              </div>
              <DialogFooter>
                <Button onClick={() => setDetailsOpen(false)}>Close</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          <TabsContent value="programme-candidates">
            <Card className="theme-panel">
              <CardHeader>
                <CardTitle className="theme-title flex items-center gap-2">Programme Discovery</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <p className="theme-muted text-sm">Aggregated unlisted programme submissions grouped by normalized value. Use these tools to verify aliases or reject noisy entries.</p>
                  <div>
                    <Button onClick={async () => { try { setLoading(true); const res = await fetchProgrammeCandidatesDetailed(); setProgrammeCandidates(res.items); } finally { setLoading(false); } }}>Refresh candidates</Button>
                  </div>
                {programmeCandidates.length === 0 ? (
                  <p className="theme-muted">No programme candidates found.</p>
                ) : (
                  <div className="grid gap-4">
                    {programmeCandidates.map((item: ProgrammeCandidateItem) => (
                      <div key={`${item.normalized_programme_name}-${item.school_id}`} className="theme-soft-panel rounded-xl p-4">
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="theme-title">{item.normalized_programme_name}</p>
                            <p className="theme-muted text-sm">Occurrences: {item.occurrences} · School: {item.school_id} · College: {item.college_id} · Campus: {item.campus_id}</p>
                          </div>
                          <div className="flex gap-2">
                            {item.best_match ? <Badge>{item.best_match.name} · {item.best_match.confidence}%</Badge> : null}
                            <Button variant="outline" onClick={async () => {
                              if (!confirm(`Verify alias for \"${item.normalized_programme_name}\" to the best match ${item.best_match?.name || ''}?`)) return;
                              try {
                                setLoading(true);
                                const target = item.best_match?.id;
                                if (!target) { alert('No recommended programme available'); return; }
                                await verifyProgrammeCandidate({ normalized_programme_name: item.normalized_programme_name, campus_id: item.campus_id, college_id: item.college_id, school_id: item.school_id, programme_id: target });
                                alert('Alias verified');
                              } catch (e) { console.error(e); alert('Failed to verify alias'); } finally { setLoading(false); }
                            }}>Verify Alias</Button>
                            <Button variant="outline" onClick={async () => {
                              try {
                                setLoading(true);
                                const res = await fetchProgrammeCandidateSubmissions(item.normalized_programme_name);
                                setSelectedCandidateSubmissions(res.items || []);
                                setSelectedCandidateName(item.normalized_programme_name);
                                setDetailsOpen(true);
                              } catch (e) { console.error(e); alert('Failed to load submissions'); } finally { setLoading(false); }
                            }}>View Details</Button>
                            <Button variant="destructive" onClick={async () => {
                              if (!confirm(`Reject all submissions for \"${item.normalized_programme_name}\" in this context?`)) return;
                              try { setLoading(true); await rejectProgrammeCandidateGroup({ normalized_programme_name: item.normalized_programme_name, campus_id: item.campus_id, college_id: item.college_id, school_id: item.school_id }); alert('Rejected'); } catch (e) { console.error(e); alert('Failed'); } finally { setLoading(false); }
                            }}>Reject</Button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="role-requests">
          <Card className="theme-panel">
            <CardHeader>
              <CardTitle className="theme-title flex items-center gap-2">
                <Clock className="theme-section-icon h-5 w-5" />
                CP and Lecturer Approval Requests
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="relative">
                <Search className="theme-muted absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2" />
                <Input
                  value={userSearch}
                  onChange={(event) => setUserSearch(event.target.value)}
                  placeholder="Search pending requests by name, email, requested role, or UR code..."
                  className="pl-10"
                />
              </div>

              {loading ? (
                <div className="grid gap-4 md:grid-cols-2">
                  {[1, 2].map((item) => (
                    <div key={item} className="h-36 animate-pulse rounded-2xl bg-muted" />
                  ))}
                </div>
              ) : filteredRoleRequests.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-border px-6 py-12 text-center text-sm text-muted-foreground">
                  No pending CP or lecturer requests right now.
                </div>
              ) : (
                <>
                <div className="grid gap-4 xl:grid-cols-2">
                  {paginatedRoleRequests.map((profile) => (
                    <Card key={profile.id} className="border-border/80 bg-card/85">
                      <CardContent className="space-y-4 p-5">
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                          <div>
                            <div className="mb-2 flex flex-wrap items-center gap-2">
                              <h3 className="text-lg font-semibold text-foreground">{profile.display_name}</h3>
                              <RoleBadge role={profile.role} />
                              <RequestedRoleBadge requestedRole={profile.requested_role} requestedRoleStatus={profile.requested_role_status} />
                            </div>
                            <p className="text-sm text-muted-foreground">{profile.email || 'No email saved'}</p>
                            <p className="mt-2 text-sm text-muted-foreground">
                              {profile.institution_type === 'ur_student'
                                ? `University of Rwanda - ${profile.ur_student_code || 'UR code missing'}`
                                : profile.university_name || 'University not specified'}
                            </p>
                          </div>
                          <Button variant="outline" size="sm" onClick={() => openUserDialog(profile)}>
                            View details
                          </Button>
                        </div>

                        <div className="grid gap-2 text-sm text-muted-foreground sm:grid-cols-2">
                          <p>Requested role: <span className="font-medium text-foreground">{profile.requested_role || 'Not set'}</span></p>
                          <p>Current role: <span className="font-medium text-foreground">{profile.role}</span></p>
                          <p>Trust score: <span className="font-medium text-foreground">{profile.trust_score || 0}</span></p>
                          <p>Joined: <span className="font-medium text-foreground">{formatDate(profile.created_at)}</span></p>
                        </div>

                        <div className="flex flex-wrap gap-2">
                          <Button
                            size="sm"
                            onClick={() => void handleRoleRequestReview(profile.id, 'approve')}
                            className="bg-success text-success-foreground hover:bg-success/90"
                          >
                            Approve
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => void handleRoleRequestReview(profile.id, 'reject')}
                          >
                            Reject
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
                <div className="mt-4 flex items-center justify-center gap-2">
                  <Button disabled={roleRequestPage <= 1} onClick={() => setRoleRequestPage((p) => Math.max(1, p - 1))}>{'<'}</Button>
                  <div className="text-sm">Page {roleRequestPage} / {roleRequestPageCount}</div>
                  <Button disabled={roleRequestPage >= roleRequestPageCount} onClick={() => setRoleRequestPage((p) => Math.min(roleRequestPageCount, p + 1))}>{'>'}</Button>
                </div>
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="reports">
          <Card className="theme-panel">
            <CardHeader>
              <CardTitle className="theme-title flex items-center gap-2">
                <Flag className="theme-section-icon h-5 w-5" />
                Recent Reports
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {overview?.recent_reports?.length ? (
                overview.recent_reports.slice(0, 10).map((report) => (
                  <div key={report.id} className="rounded-2xl border border-border bg-card/80 p-4">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <p className="text-sm font-medium text-foreground">Paper #{report.paper_id}</p>
                        <p className="mt-1 text-sm text-muted-foreground">{report.reason}</p>
                        <p className="mt-2 text-xs text-muted-foreground">
                          Status: {report.status || 'pending'} - {formatDate(report.created_at)}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          onClick={() => updateAdminReport(report.id, { status: 'resolved', hide_paper: false }).then(() => loadData())}
                          className="bg-success text-success-foreground hover:bg-success/90"
                        >
                          Resolve
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => updateAdminReport(report.id, { status: 'actioned', hide_paper: true }).then(() => loadData())}
                        >
                          Hide paper
                        </Button>
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-2xl border border-dashed border-border px-6 py-12 text-center text-sm text-muted-foreground">
                  No recent reports to review.
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="papers" className="space-y-4">
          <div className="relative">
            <Search className="theme-muted absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2" />
            <Input
              value={paperSearch}
              onChange={(event) => setPaperSearch(event.target.value)}
              placeholder="Search papers by title, course, code, or lecturer..."
              className="pl-10"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 md:grid-cols-4">
            <Card className="theme-panel">
              <CardContent className="p-4 text-center">
                <p className="text-lg font-semibold text-foreground">{pendingPapers.length}</p>
                <p className="text-xs text-muted-foreground">Pending</p>
              </CardContent>
            </Card>
            <Card className="theme-panel">
              <CardContent className="p-4 text-center">
                <p className="text-lg font-semibold text-foreground">{reportedPapers.length}</p>
                <p className="text-xs text-muted-foreground">Reported</p>
              </CardContent>
            </Card>
            <Card className="theme-panel">
              <CardContent className="p-4 text-center">
                <p className="text-lg font-semibold text-foreground">{hiddenPapers.length}</p>
                <p className="text-xs text-muted-foreground">Hidden</p>
              </CardContent>
            </Card>
            <Card className="theme-panel">
              <CardContent className="p-4 text-center">
                <p className="text-lg font-semibold text-foreground">{filteredPapers.length}</p>
                <p className="text-xs text-muted-foreground">Shown</p>
              </CardContent>
            </Card>
          </div>

            <div className="space-y-3">
            {paginatedPapers.map((paper) => (
              <Card key={paper.id} className="theme-panel">
                <CardContent className="flex flex-col gap-4 p-4 lg:flex-row lg:items-center">
                  <div className="min-w-0 flex-1">
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <h4 className="theme-title truncate font-medium">{paper.title}</h4>
                      <PaperVerificationBadge status={paper.verification_status} />
                      {paper.is_hidden && <Badge className="theme-error-note border-0">hidden</Badge>}
                    </div>
                    <div className="flex items-center gap-3 mb-2">
                      <div className="h-8 w-8 overflow-hidden rounded-full">
                        <AvatarFallback
                          name={uploaderProfiles[paper.user_id]?.profile?.display_name || paper.uploader_display_name || `Uploader ${paper.user_id}`}
                          imageUrl={uploaderProfiles[paper.user_id]?.imageUrl ?? undefined}
                          imageAlt={`${uploaderProfiles[paper.user_id]?.profile?.display_name || paper.uploader_display_name || 'Uploader'} avatar`}
                        />
                      </div>
                      <div className="text-xs theme-muted">
                        <div className="font-medium text-sm">{uploaderProfiles[paper.user_id]?.profile?.display_name || paper.uploader_display_name || `Uploader ${paper.user_id}`}</div>
                        <div>{paper.course_code} · {paper.year}</div>
                      </div>
                    </div>
                    <div className="theme-muted flex flex-wrap items-center gap-3 text-xs">
                      <span>{paper.course_code}</span>
                      <span>{paper.paper_type}</span>
                      <span>{paper.year}</span>
                      <span className="flex items-center gap-1">
                        <Download className="h-3 w-3" />
                        {paper.download_count || 0}
                      </span>
                      {(paper.report_count || 0) > 0 && (
                        <span className="flex items-center gap-1 text-error">
                          <Flag className="h-3 w-3" />
                          {paper.report_count} reports
                        </span>
                      )}
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {paper.created_at ? new Date(paper.created_at).toLocaleDateString() : 'N/A'}
                      </span>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {paper.verification_status !== 'verified' && (
                      <Button size="sm" onClick={() => handleVerifyPaper(paper.id)} className="bg-success text-success-foreground hover:bg-success/90">
                        <CheckCircle className="mr-1 h-4 w-4" />
                        Verify
                      </Button>
                    )}
                    <Button size="sm" variant="outline" onClick={() => handleTogglePaperVisibility(paper.id, !!paper.is_hidden)}>
                      {paper.is_hidden ? (
                        <>
                          <Eye className="mr-1 h-4 w-4" />
                          Show
                        </>
                      ) : (
                        <>
                          <EyeOff className="mr-1 h-4 w-4" />
                          Hide
                        </>
                      )}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => navigate(`/paper/${paper.id}`)}>
                      <Eye className="h-4 w-4" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
          <div className="mt-4 flex items-center justify-center gap-2">
            <Button disabled={paperPage <= 1} onClick={() => setPaperPage((p) => Math.max(1, p - 1))}>{'<'}</Button>
            <div className="text-sm">Page {paperPage} / {paperPageCount}</div>
            <Button disabled={paperPage >= paperPageCount} onClick={() => setPaperPage((p) => Math.min(paperPageCount, p + 1))}>{'>'}</Button>
          </div>
        </TabsContent>
      </Tabs>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{selectedUser?.display_name || 'User details'}</DialogTitle>
            <DialogDescription>
              Review the complete user profile, update role and verification, or remove the account when needed.
            </DialogDescription>
          </DialogHeader>

          {draft && selectedUser && (
            <div className="space-y-6">
              <div className="grid gap-3 rounded-2xl bg-muted/40 p-4 text-sm md:grid-cols-3">
                <div>
                  <p className="text-muted-foreground">User ID</p>
                  <p className="mt-1 break-all font-medium text-foreground">{selectedUser.user_id}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Joined</p>
                  <p className="mt-1 font-medium text-foreground">{formatDate(selectedUser.created_at)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Last login</p>
                  <p className="mt-1 font-medium text-foreground">{formatDate(selectedUser.last_login)}</p>
                </div>
              </div>

              {adminProtected && (
                <div className="rounded-2xl border border-warning-border bg-warning-soft px-4 py-3 text-sm text-warning-foreground">
                  Only administrators can edit or delete administrator accounts.
                </div>
              )}

              {selectedUser.requested_role && selectedUser.requested_role_status && selectedUser.requested_role_status !== 'none' && (
                <div className="rounded-2xl border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
                  Requested privileged role:
                  <span className="ml-2 font-medium text-foreground">
                    {selectedUser.requested_role}
                  </span>
                  <span className="ml-2">status:</span>
                  <span className="ml-2 font-medium text-foreground">{selectedUser.requested_role_status}</span>
                </div>
              )}

              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <Label htmlFor="user-display-name">Display name</Label>
                  <Input id="user-display-name" value={draft.display_name} onChange={(event) => updateDraft('display_name', event.target.value)} disabled={adminProtected} />
                </div>
                <div>
                  <Label htmlFor="user-email">Email</Label>
                  <Input id="user-email" value={draft.email} onChange={(event) => updateDraft('email', event.target.value)} disabled={adminProtected} />
                </div>
                <div>
                  <Label>Role</Label>
                  <Select value={draft.role} onValueChange={(value) => updateDraft('role', value)} disabled={adminProtected}>
                    <SelectTrigger className="mt-2">
                      <SelectValue placeholder="Choose a role" />
                    </SelectTrigger>
                    <SelectContent>
                      {roleOptions.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Account status</Label>
                  <Select value={draft.account_status} onValueChange={(value) => updateDraft('account_status', value)} disabled={adminProtected}>
                    <SelectTrigger className="mt-2">
                      <SelectValue placeholder="Choose a status" />
                    </SelectTrigger>
                    <SelectContent>
                      {STATUS_OPTIONS.map((option) => (
                        <SelectItem key={option} value={option}>
                          {option}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="user-trust-score">Trust score</Label>
                  <Input id="user-trust-score" type="number" value={draft.trust_score} onChange={(event) => updateDraft('trust_score', event.target.value)} disabled={adminProtected} />
                </div>
                <div>
                  <Label>UR verification</Label>
                  <Select value={draft.ur_verification_status} onValueChange={(value) => updateDraft('ur_verification_status', value)} disabled={adminProtected}>
                    <SelectTrigger className="mt-2">
                      <SelectValue placeholder="Choose verification status" />
                    </SelectTrigger>
                    <SelectContent>
                      {UR_OPTIONS.map((option) => (
                        <SelectItem key={option} value={option}>
                          {option}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Institution type</Label>
                  <Select value={draft.institution_type} onValueChange={(value) => updateDraft('institution_type', value)} disabled={adminProtected}>
                    <SelectTrigger className="mt-2">
                      <SelectValue placeholder="Choose institution type" />
                    </SelectTrigger>
                    <SelectContent>
                      {INSTITUTION_OPTIONS.map((option) => (
                        <SelectItem key={option} value={option}>
                          {option}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="user-university">University</Label>
                  <Input id="user-university" value={draft.university_name} onChange={(event) => updateDraft('university_name', event.target.value)} disabled={adminProtected} />
                </div>
                <div>
                  <Label htmlFor="user-ur-code">UR student code</Label>
                  <Input id="user-ur-code" value={draft.ur_student_code} onChange={(event) => updateDraft('ur_student_code', event.target.value)} disabled={adminProtected} />
                </div>
                <div>
                  <Label htmlFor="user-phone">Phone number</Label>
                  <Input id="user-phone" value={draft.phone_number} onChange={(event) => updateDraft('phone_number', event.target.value)} disabled={adminProtected} />
                </div>
                <div>
                  <Label htmlFor="user-college">College</Label>
                  <Input id="user-college" value={draft.college_name} onChange={(event) => updateDraft('college_name', event.target.value)} disabled={adminProtected} />
                </div>
                <div>
                  <Label htmlFor="user-department">Department</Label>
                  <Input id="user-department" value={draft.department_name} onChange={(event) => updateDraft('department_name', event.target.value)} disabled={adminProtected} />
                </div>
                <div>
                  <Label htmlFor="user-year">Year of study</Label>
                  <Input id="user-year" value={draft.year_of_study} onChange={(event) => updateDraft('year_of_study', event.target.value)} disabled={adminProtected} />
                </div>
                <div className="md:col-span-2">
                  <Label htmlFor="user-suspension-reason">Suspension reason</Label>
                  <Input id="user-suspension-reason" value={draft.suspension_reason} onChange={(event) => updateDraft('suspension_reason', event.target.value)} disabled={adminProtected} />
                </div>
                <div className="md:col-span-2">
                  <Label htmlFor="user-bio">Bio</Label>
                  <Textarea id="user-bio" value={draft.bio} onChange={(event) => updateDraft('bio', event.target.value)} disabled={adminProtected} className="min-h-[120px]" />
                </div>
              </div>
          <DialogFooter className="gap-3">
            <Button
              variant="destructive"
              onClick={() => void handleDeleteUser()}
              disabled={adminProtected || deleting || selectedUser?.user_id === user.id}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              {deleting ? 'Deleting...' : 'Delete user'}
            </Button>
            <Button onClick={() => void handleSaveUser()} disabled={adminProtected || saving}>
              {saving ? 'Saving...' : 'Save changes'}
            </Button>
          </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
