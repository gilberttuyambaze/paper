import { ChangeEvent, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  fetchUserProfile,
  fetchAcademicTaxonomy,
  getStorageDownloadUrl,
  updateUserProfile,
  uploadFileObject,
  clearResolvedPublicProfile,
  type UserProfile,
} from '../lib/client';
import { authApi } from '../lib/auth';
import { useAuth } from '../contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { BadgeCheck, Camera, Eye, EyeOff, KeyRound, Pencil, School, ShieldCheck } from 'lucide-react';
import { toast } from '@/lib/messages';
import AvatarFallback from '../components/AvatarFallback';
import AcademicContextFields from '../components/AcademicContextFields';
import InlineFieldMessage from '../components/InlineFieldMessage';
import {
  buildProfilePictureObjectKey,
  createEmptyProfileForm,
  institutionTypeOptions,
  normalizeOptionalField,
  yearOfStudyOptions,
  type ProfileFormValues,
} from '../lib/profile-form';

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
  if (status === 'rejected') {
    return <Badge className="bg-error-soft text-error-foreground hover:bg-error-soft">UR verification rejected</Badge>;
  }
  return <Badge className="theme-soft-panel  hover:bg-inherit">No UR verification</Badge>;
}

function profileFormFromProfile(profile: UserProfile, fallbackName: string): ProfileFormValues {
  const inferredInstitutionType =
    profile.institution_type || (profile.ur_student_code ? 'ur_student' : 'other_university');

  return {
    display_name: profile.display_name || fallbackName,
    institution_type: inferredInstitutionType,
    university_name:
      inferredInstitutionType === 'ur_student'
        ? 'University of Rwanda'
        : profile.university_name || '',
    ur_student_code: profile.ur_student_code || '',
    phone_number: profile.phone_number || '',
    college_name: profile.college_name || '',
    department_name: profile.department_name || '',
    institution_id: profile.institution_id || 'ur', campus_id: profile.campus_id || '', college_id: profile.college_id || '', school_id: profile.school_id || '', programme_id: profile.programme_id || '',
    programme_name_other: profile.programme_name_other || '',
    year_of_study: profile.year_of_study || '',
    bio: profile.bio || '',
  };
}

export default function ProfilePage() {
  const navigate = useNavigate();
  const { user, loading: authLoading, refetch } = useAuth();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [profileForm, setProfileForm] = useState<ProfileFormValues>(createEmptyProfileForm());
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [profileImageUrl, setProfileImageUrl] = useState<string | null>(null);
  const [profileImageFile, setProfileImageFile] = useState<File | null>(null);
  const [profileImagePreview, setProfileImagePreview] = useState<string | null>(null);
  const [profileImageUrlInput, setProfileImageUrlInput] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [academicNames, setAcademicNames] = useState<Record<string, string>>({});
  const [touchedFields, setTouchedFields] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!user) {
      setProfile(null);
      setLoading(false);
      return;
    }

    void loadProfile();
  }, [user]);

  useEffect(() => {
    void fetchAcademicTaxonomy().then((taxonomy) => setAcademicNames(Object.fromEntries(taxonomy.nodes.map((node) => [node.id, node.name])))).catch(() => setAcademicNames({}));
  }, []);

  useEffect(() => {
    let cancelled = false;

    if (!profile?.profile_picture_key) {
      setProfileImageUrl(null);
      return () => {
        cancelled = true;
      };
    }

    // If profile_picture_key is an external URL, use it directly.
    if (/^https?:\/\//i.test(profile.profile_picture_key)) {
      setProfileImageUrl(profile.profile_picture_key);
      return () => {
        cancelled = true;
      };
    }

    void getStorageDownloadUrl('profiles', profile.profile_picture_key)
      .then((url) => {
        if (!cancelled) {
          setProfileImageUrl(url);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setProfileImageUrl(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [profile?.profile_picture_key]);

  const loadProfile = async () => {
    try {
      setLoading(true);
      const currentProfile = await fetchUserProfile();
      if (currentProfile) {
        setProfile(currentProfile);
        setProfileForm(profileFormFromProfile(currentProfile, user?.name || ''));
      }
    } catch (err) {
      console.error('Failed to load profile:', err);
      toast.error('Failed to load your profile');
    } finally {
      setLoading(false);
    }
  };

  const updateField = <K extends keyof ProfileFormValues>(field: K, value: ProfileFormValues[K]) => {
    setTouchedFields((current) => ({ ...current, [field]: true }));
    setProfileForm((prev) => {
      const next = { ...prev, [field]: value };
      if (field === 'institution_type') {
        if (value === 'ur_student') {
          next.university_name = 'University of Rwanda';
        } else if (prev.university_name === 'University of Rwanda') {
          next.university_name = '';
        }
      }
      return next;
    });
  };

  const handleProfileImageChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] || null;
    setProfileImageFile(file);

    if (profileImagePreview?.startsWith('blob:')) {
      URL.revokeObjectURL(profileImagePreview);
    }

    if (!file) {
      setProfileImagePreview(null);
      return;
    }

    setProfileImagePreview(URL.createObjectURL(file));
  };

  const handleCancelEdit = () => {
    if (profile) {
      setProfileForm(profileFormFromProfile(profile, user?.name || ''));
    }
    if (profileImagePreview?.startsWith('blob:')) {
      URL.revokeObjectURL(profileImagePreview);
    }
    setProfileImagePreview(null);
    setProfileImageFile(null);
    setEditing(false);
  };

  const handleSavePassword = async () => {
    if (!user) return;

    if (password.length < 6) {
      toast.error('Password is too weak. Use at least 6 characters.');
      return;
    }

    if (password !== confirmPassword) {
      toast.error('Passwords do not match.');
      return;
    }

    setPasswordSaving(true);
    try {
      await authApi.setPassword(password);
      setPassword('');
      setConfirmPassword('');
      setShowPassword(false);
      setShowConfirmPassword(false);
      toast.success('Password updated successfully.');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unable to update password.';
      toast.error(message);
    } finally {
      setPasswordSaving(false);
    }
  };

  const handleSaveProfile = async () => {
    if (!user || !profile) return;

    const displayName = profileForm.display_name.trim();
    const isUrStudent = profileForm.institution_type === 'ur_student';
    const urCodeLocked = profile.ur_verification_status === 'verified';

    if (!displayName) {
      toast.error('Full name is required.');
      return;
    }

    if (isUrStudent && !urCodeLocked && !profileForm.ur_student_code.trim()) {
      toast.error('UR student code is required for UR verification.');
      return;
    }

    if (!isUrStudent && !urCodeLocked && !profileForm.university_name.trim()) {
      toast.error('University name is required when selecting another university.');
      return;
    }

    setSaving(true);
    try {
      const updatePayload: Parameters<typeof updateUserProfile>[0] = {
        display_name: displayName,
        phone_number: normalizeOptionalField(profileForm.phone_number),
        college_name: normalizeOptionalField(profileForm.college_name),
        department_name: normalizeOptionalField(profileForm.department_name),
        institution_id: profileForm.campus_id ? 'ur' : undefined,
        campus_id: normalizeOptionalField(profileForm.campus_id), college_id: normalizeOptionalField(profileForm.college_id), school_id: normalizeOptionalField(profileForm.school_id), programme_id: normalizeOptionalField(profileForm.programme_id),
        programme_name_other: profileForm.programme_id === 'other' ? normalizeOptionalField(profileForm.programme_name_other) : undefined,
        year_of_study: normalizeOptionalField(profileForm.year_of_study),
        bio: normalizeOptionalField(profileForm.bio),
      };

      if (!urCodeLocked) {
        updatePayload.institution_type = profileForm.institution_type;
        updatePayload.university_name =
          isUrStudent ? 'University of Rwanda' : normalizeOptionalField(profileForm.university_name);
        updatePayload.ur_student_code =
          isUrStudent ? normalizeOptionalField(profileForm.ur_student_code) : undefined;
      }

      if (profileImageFile) {
        const objectKey = buildProfilePictureObjectKey(user.id, profileImageFile.name);
        updatePayload.profile_picture_key = await uploadFileObject('profiles', objectKey, profileImageFile);
      } else if (profileImageUrlInput.trim()) {
        updatePayload.profile_picture_key = profileImageUrlInput.trim();
      }

      const updatedProfile = await updateUserProfile(updatePayload);
      setProfile(updatedProfile);
      setProfileForm(profileFormFromProfile(updatedProfile, displayName));
      if (profileImagePreview?.startsWith('blob:')) {
        URL.revokeObjectURL(profileImagePreview);
      }
      setProfileImagePreview(null);
      setProfileImageFile(null);
      setEditing(false);
      await refetch();
      // Clear cached resolved public profile so other views refresh avatar/display name
      try {
        clearResolvedPublicProfile(user.id);
      } catch {
        // ignore
      }
      toast.success('Profile updated');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update profile';
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  if (authLoading || loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="theme-spinner h-8 w-8 animate-spin rounded-full border-b-2 border-current" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 text-center">
        <h2 className="theme-title mb-4 text-2xl font-bold">Sign In Required</h2>
        <p className="theme-muted mb-6">
          Sign in to view and manage your profile.
        </p>
        <Button onClick={() => authApi.login('/profile')} className="theme-accent-bg">
          Sign In
        </Button>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16">
        <Card className="theme-panel">
          <CardContent className="p-10 text-center">
            <p className="theme-muted">We could not load your profile right now.</p>
            <Button onClick={() => void loadProfile()} className="theme-accent-bg mt-4">
              Try again
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const urCodeLocked = profile.ur_verification_status === 'verified';
  const previewImage = profileImagePreview || profileImageUrl;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="theme-title text-3xl font-bold">My Profile</h1>
          <p className="theme-muted mt-1">
            View your academic identity, community details, and verification status in one place.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant="secondary">{profile.role || 'normal'}</Badge>
          <URVerificationBadge status={profile.ur_verification_status} />
          <Badge variant="outline">
            {profile.account_status || 'active'}
          </Badge>
          {!editing ? (
            <Button onClick={() => setEditing(true)} className="theme-accent-bg">
              <Pencil className="mr-2 h-4 w-4" />
              Edit profile
            </Button>
          ) : (
            <Button variant="outline" onClick={handleCancelEdit}>
              Cancel
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
        <Card className="theme-panel">
          <CardContent className="p-6">
            <div className="theme-accent-soft mx-auto h-36 w-36 overflow-hidden rounded-[2rem] text-4xl">
              <AvatarFallback name={profile.display_name} imageUrl={previewImage} imageAlt="Your profile picture" />
            </div>

            <div className="mt-5 text-center">
              <h2 className="theme-title text-2xl font-semibold">{profile.display_name}</h2>
              <p className="theme-muted mt-1 text-sm">{user.email}</p>
            </div>

            <div className="theme-soft-panel mt-5 space-y-3 rounded-2xl p-4 text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="theme-muted">Institution</span>
                <span className="theme-title text-right font-medium">
                  {profile.institution_type === 'ur_student' ? 'University of Rwanda' : profile.university_name || 'Not set'}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="theme-muted">UR status</span>
                <span className="theme-title text-right font-medium">
                  {profile.ur_verification_status || 'not_requested'}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="theme-muted">Trust score</span>
                <span className="theme-title text-right font-medium">
                  {profile.trust_score || 0}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="theme-muted">Uploads</span>
                <span className="theme-title text-right font-medium">
                  {profile.upload_count || 0}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="theme-muted">Downloads</span>
                <span className="theme-title text-right font-medium">
                  {profile.download_count || 0}
                </span>
              </div>
            </div>

            {editing && (
              <div className="mt-5">
                <Label htmlFor="profile-image" className="theme-form-label">Profile picture</Label>
                <Input
                  id="profile-image"
                  type="file"
                  accept="image/*"
                  onChange={handleProfileImageChange}
                  className="theme-form-input mt-2 h-11 rounded-xl cursor-pointer"
                />
                <div className="mt-2">
                  <Input
                    id="profile-image"
                    type="file"
                    accept="image/*"
                    onChange={handleProfileImageChange}
                    className="theme-form-input h-11 rounded-xl cursor-pointer w-full"
                  />
                </div>

                <div className="mt-3 flex items-center gap-2">
                  <Input
                    placeholder="Or paste image URL"
                    value={profileImageUrlInput}
                    onChange={(e) => setProfileImageUrlInput(e.target.value)}
                    className="theme-form-input h-11 rounded-xl flex-1"
                  />
                  <Button
                    type="button"
                    onClick={() => {
                      const url = profileImageUrlInput.trim();
                      if (!url) return;
                      setProfileImageFile(null);
                      setProfileImagePreview(url);
                    }}
                  >
                    Use URL
                  </Button>
                </div>
                <p className="theme-muted mt-2 text-xs">
                  Upload a photo or logo to make your profile easier to recognize.
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        {!editing ? (
          <Card className="theme-panel">
            <CardHeader>
              <CardTitle className="theme-title flex items-center gap-2">
                <School className="theme-section-icon h-5 w-5" />
                Profile Details
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
              <ReadOnlyField label="UR student code" value={profile.ur_student_code} />
              <ReadOnlyField label="Phone number" value={profile.phone_number} />
              {profile.campus_id && <ReadOnlyField label="Campus" value={academicNames[profile.campus_id]} />}
              <ReadOnlyField label="College" value={profile.college_name} />
              {profile.school_id && <ReadOnlyField label="School" value={academicNames[profile.school_id]} />}
              {profile.programme_id && <ReadOnlyField label="Academic programme" value={profile.programme_id === 'other' ? 'Programme not listed' : academicNames[profile.programme_id]} />}
              <ReadOnlyField label="Department" value={profile.department_name} />
              <ReadOnlyField label="Year of study" value={profile.year_of_study} />
              <div className="md:col-span-2">
                <ReadOnlyField label="Bio" value={profile.bio} multiline />
              </div>
              <div className="theme-auth-subtle md:col-span-2 rounded-2xl p-4 text-sm">
                {urCodeLocked ? (
                  <div className="flex items-start gap-3">
                    <ShieldCheck className="mt-0.5 h-5 w-5 text-success-foreground" />
                    <p>Your UR student code has been verified and is now locked to preserve verification integrity.</p>
                  </div>
                ) : (
                  <p>
                    Your profile is currently in view mode. Click <span className="font-semibold">Edit profile</span> to update your details.
                  </p>
                )}
              </div>
            </CardContent>
          </Card>
        ) : (
          <Card className="theme-panel">
            <CardHeader>
              <CardTitle className="theme-title flex items-center gap-2">
                <Camera className="theme-section-icon h-5 w-5" />
                Edit Profile
              </CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              <div>
                <Label htmlFor="display_name" className="theme-form-label">Full Name</Label>
                <Input
                  id="display_name"
                  value={profileForm.display_name}
                  onChange={(event) => updateField('display_name', event.target.value)}
                  onBlur={() => setTouchedFields((current) => ({ ...current, display_name: true }))}
                  aria-invalid={Boolean(touchedFields.display_name && !profileForm.display_name.trim())}
                  aria-describedby="profile-display-name-error"
                  className="theme-form-input mt-2 h-11 rounded-xl"
                />
                <InlineFieldMessage id="profile-display-name-error" message={touchedFields.display_name && !profileForm.display_name.trim() ? 'Full name is required.' : undefined} />
              </div>

              <div>
                <Label className="theme-form-label">Student type</Label>
                <Select
                  value={profileForm.institution_type}
                  onValueChange={(value) => updateField('institution_type', value as ProfileFormValues['institution_type'])}
                  disabled={urCodeLocked}
                >
                  <SelectTrigger className="theme-form-input mt-2 h-11 rounded-xl disabled:opacity-80">
                    <SelectValue placeholder="Choose your institution type" />
                  </SelectTrigger>
                  <SelectContent>
                    {institutionTypeOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label htmlFor="university_name" className="theme-form-label">University</Label>
                <Input
                  id="university_name"
                  value={profileForm.institution_type === 'ur_student' ? 'University of Rwanda' : profileForm.university_name}
                  onChange={(event) => updateField('university_name', event.target.value)}
                  disabled={profileForm.institution_type === 'ur_student' || urCodeLocked}
                  aria-invalid={Boolean(touchedFields.university_name && !urCodeLocked && profileForm.institution_type !== 'ur_student' && !profileForm.university_name.trim())}
                  aria-describedby="profile-university-error"
                  className="theme-form-input mt-2 h-11 rounded-xl disabled:opacity-80"
                />
                <InlineFieldMessage id="profile-university-error" message={touchedFields.university_name && !urCodeLocked && profileForm.institution_type !== 'ur_student' && !profileForm.university_name.trim() ? 'University name is required.' : undefined} />
              </div>

              <div>
                <Label htmlFor="ur_student_code" className="theme-form-label">UR Student Code</Label>
                <Input
                  id="ur_student_code"
                  value={profileForm.ur_student_code}
                  onChange={(event) => updateField('ur_student_code', event.target.value)}
                  disabled={profileForm.institution_type !== 'ur_student' || urCodeLocked}
                  placeholder={urCodeLocked ? 'Verified code is locked' : 'Required for UR verification'}
                  aria-invalid={Boolean(touchedFields.ur_student_code && !urCodeLocked && profileForm.institution_type === 'ur_student' && !profileForm.ur_student_code.trim())}
                  aria-describedby="profile-student-code-error"
                  className="theme-form-input mt-2 h-11 rounded-xl disabled:opacity-80"
                />
                <InlineFieldMessage id="profile-student-code-error" message={touchedFields.ur_student_code && !urCodeLocked && profileForm.institution_type === 'ur_student' && !profileForm.ur_student_code.trim() ? 'UR student code is required for verification.' : undefined} />
              </div>

              <div>
                <Label htmlFor="phone_number" className="theme-form-label">Phone Number</Label>
                <Input
                  id="phone_number"
                  value={profileForm.phone_number}
                  onChange={(event) => updateField('phone_number', event.target.value)}
                  className="theme-form-input mt-2 h-11 rounded-xl"
                />
              </div>

              <div className="sm:col-span-2"><AcademicContextFields value={profileForm} onChange={(academic) => setProfileForm((current) => ({ ...current, ...academic }))} otherName={profileForm.programme_name_other} onOtherNameChange={(programme_name_other) => updateField('programme_name_other', programme_name_other)} submissionSource="profile" /></div>

              <div>
                <Label className="theme-form-label">Year of study</Label>
                <Select value={profileForm.year_of_study} onValueChange={(value) => updateField('year_of_study', value)}>
                  <SelectTrigger className="theme-form-input mt-2 h-11 rounded-xl">
                    <SelectValue placeholder="Select your current year" />
                  </SelectTrigger>
                  <SelectContent>
                    {yearOfStudyOptions.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="md:col-span-2">
                <Label htmlFor="bio" className="theme-form-label">Short Bio</Label>
                <Textarea
                  id="bio"
                  value={profileForm.bio}
                  onChange={(event) => updateField('bio', event.target.value)}
                  className="theme-form-input mt-2 min-h-[120px] rounded-2xl"
                />
              </div>

              <div className="theme-auth-subtle md:col-span-2 rounded-2xl p-4 text-sm">
                {urCodeLocked ? (
                  <p>Your UR student code has been verified. The code, institution type, and university are now locked.</p>
                ) : (
                  <p>If you use a UR student code, your verification status will stay pending until it is reviewed.</p>
                )}
              </div>

              <div className="md:col-span-2 flex justify-end gap-3">
                <Button variant="outline" onClick={handleCancelEdit}>
                  Cancel
                </Button>
                <Button onClick={handleSaveProfile} disabled={saving} className="theme-accent-bg">
                  {saving ? 'Saving...' : 'Save profile'}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Dedicated Password & Security Card */}
        <Card className="theme-panel mt-6">
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <CardTitle className="theme-title flex items-center gap-2 text-lg">
                <KeyRound className="theme-section-icon h-5 w-5" />
                Password & Security
              </CardTitle>
              <Badge variant={user?.email ? 'secondary' : 'outline'}>
                {user?.email ? 'Email / Password login enabled' : 'Google sign-in'}
              </Badge>
            </div>
            <p className="theme-muted text-xs">
              Set or update your account password to sign in directly using your email address and password.
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <Label className="theme-form-label">New password</Label>
                <div className="relative mt-2">
                  <Input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    onBlur={() => setTouchedFields((current) => ({ ...current, password: true }))}
                    aria-invalid={Boolean(touchedFields.password && password && password.length < 6)}
                    aria-describedby="profile-password-error"
                    placeholder="At least 6 characters"
                    className="theme-form-input h-11 rounded-xl pr-12"
                  />
                  <button
                    type="button"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    onClick={() => setShowPassword((value) => !value)}
                    className="absolute inset-y-0 right-3 flex items-center text-muted-foreground hover:text-foreground"
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <InlineFieldMessage id="profile-password-error" message={touchedFields.password && password && password.length < 6 ? 'Password must contain at least 6 characters.' : undefined} />
              </div>
              <div>
                <Label className="theme-form-label">Confirm password</Label>
                <div className="relative mt-2">
                  <Input
                    type={showConfirmPassword ? 'text' : 'password'}
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    onBlur={() => setTouchedFields((current) => ({ ...current, confirmPassword: true }))}
                    aria-invalid={Boolean(touchedFields.confirmPassword && confirmPassword && password !== confirmPassword)}
                    aria-describedby="profile-confirm-password-error"
                    placeholder="Confirm new password"
                    className="theme-form-input h-11 rounded-xl pr-12"
                  />
                  <button
                    type="button"
                    aria-label={showConfirmPassword ? 'Hide confirm password' : 'Show confirm password'}
                    onClick={() => setShowConfirmPassword((value) => !value)}
                    className="absolute inset-y-0 right-3 flex items-center text-muted-foreground hover:text-foreground"
                  >
                    {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <InlineFieldMessage id="profile-confirm-password-error" message={touchedFields.confirmPassword && confirmPassword && password !== confirmPassword ? 'Passwords do not match.' : undefined} />
              </div>
            </div>
            <div className="flex justify-end pt-2">
              <Button
                type="button"
                onClick={handleSavePassword}
                disabled={passwordSaving || !password || password.length < 6 || password !== confirmPassword}
                className="theme-accent-bg"
              >
                {passwordSaving ? 'Updating password…' : 'Update Password'}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="mt-8">
        <Button variant="outline" onClick={() => navigate('/dashboard')}>
          Back to dashboard
        </Button>
      </div>
    </div>
  );
}

function ReadOnlyField({
  label,
  value,
  multiline = false,
}: {
  label: string;
  value?: string | null;
  multiline?: boolean;
}) {
  return (
    <div className="theme-soft-panel rounded-2xl p-4">
      <p className="theme-muted text-xs font-semibold uppercase tracking-[0.2em]">{label}</p>
      <p className={`theme-title mt-2 text-sm ${multiline ? 'whitespace-pre-wrap leading-6' : ''}`}>
        {value || 'Not provided yet'}
      </p>
    </div>
  );
}
