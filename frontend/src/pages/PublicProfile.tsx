import { ReactNode, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ArrowLeft, BadgeCheck, BookOpen, School, UserCircle2 } from 'lucide-react';
import { resolvePublicUserProfile, type PublicUserProfile } from '../lib/client';
import { toast } from '@/lib/messages';
import AvatarFallback from '../components/AvatarFallback';

function URVerificationBadge({ status }: { status?: string | null }) {
  if (status === 'verified') {
    return (
      <Badge className="bg-success-soft text-success-foreground hover:bg-success-soft">
        <BadgeCheck className="mr-1 h-3 w-3" />
        UR verified
      </Badge>
    );
  }
  if (status === 'pending') {
    return <Badge className="bg-warning-soft text-warning-foreground hover:bg-warning-soft">UR review pending</Badge>;
  }
  return <Badge variant="secondary">Community profile</Badge>;
}

export default function PublicProfilePage() {
  const { userId } = useParams<{ userId: string }>();
  const navigate = useNavigate();
  const [profile, setProfile] = useState<PublicUserProfile | null>(null);
  const [profileImageUrl, setProfileImageUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!userId) return;
    void loadProfile(userId);
  }, [userId]);

  // profile image resolved by resolvePublicUserProfile during loadProfile

  const loadProfile = async (nextUserId: string) => {
    try {
      setLoading(true);
      const resolved = await resolvePublicUserProfile(nextUserId);
      setProfile(resolved.profile || null);
      setProfileImageUrl(resolved.imageUrl || null);
    } catch {
      toast.error('Failed to load uploader profile');
      setProfile(null);
      setProfileImageUrl(null);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="theme-spinner h-8 w-8 animate-spin rounded-full border-b-2 border-current" />
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 text-center">
        <h2 className="theme-title mb-4 text-2xl font-bold">Uploader Profile Not Found</h2>
        <Button onClick={() => navigate(-1)} variant="outline">Go back</Button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
      <Button variant="ghost" onClick={() => navigate(-1)} className="theme-ghost-brand-button mb-6">
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back
      </Button>

      <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
        <Card className="theme-panel">
          <CardContent className="p-6">
            <div className="theme-accent-soft mx-auto h-36 w-36 overflow-hidden rounded-full text-4xl">
              <AvatarFallback name={profile.display_name} imageUrl={profileImageUrl} imageAlt={`${profile.display_name} profile picture`} />
            </div>

            <div className="mt-5 text-center">
              <h1 className="theme-title text-2xl font-semibold">{profile.display_name}</h1>
              <p className="theme-muted mt-1 text-sm">{profile.role}</p>
            </div>

            <div className="mt-4 flex flex-wrap justify-center gap-2">
              <URVerificationBadge status={profile.ur_verification_status} />
              <Badge variant="outline">Trust {profile.trust_score || 0}</Badge>
            </div>

            <div className="theme-soft-panel mt-5 space-y-3 rounded-2xl p-4 text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="theme-muted">Uploads</span>
                <span className="theme-title font-medium">{profile.upload_count || 0}</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="theme-muted">Downloads</span>
                <span className="theme-title font-medium">{profile.download_count || 0}</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="theme-muted">Joined</span>
                <span className="theme-title font-medium">
                  {profile.created_at ? new Date(profile.created_at).toLocaleDateString() : 'N/A'}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="theme-panel">
          <CardHeader>
            <CardTitle className="theme-title flex items-center gap-2">
              <UserCircle2 className="theme-section-icon h-5 w-5" />
              Uploader Details
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            <ReadOnlyField label="Full name" value={profile.display_name} />
            <ReadOnlyField
              label="Student type"
              value={profile.institution_type === 'ur_student' ? 'University of Rwanda student' : 'Other university student'}
            />
            <ReadOnlyField
              label="University"
              value={profile.institution_type === 'ur_student' ? 'University of Rwanda' : profile.university_name}
            />
            <ReadOnlyField label="College" value={profile.college_name} icon={<School className="theme-section-icon h-4 w-4" />} />
            <ReadOnlyField label="Department" value={profile.department_name} icon={<BookOpen className="theme-section-icon h-4 w-4" />} />
            <ReadOnlyField label="Year of study" value={profile.year_of_study} />
            <div className="md:col-span-2">
              <ReadOnlyField label="Bio" value={profile.bio} multiline />
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function ReadOnlyField({
  label,
  value,
  multiline = false,
  icon,
}: {
  label: string;
  value?: string | null;
  multiline?: boolean;
  icon?: ReactNode;
}) {
  return (
    <div className="theme-soft-panel rounded-2xl p-4">
      <p className="theme-muted flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em]">
        {icon}
        {label}
      </p>
      <p className={`theme-title mt-2 text-sm ${multiline ? 'whitespace-pre-wrap leading-6' : ''}`}>
        {value || 'Not provided yet'}
      </p>
    </div>
  );
}
