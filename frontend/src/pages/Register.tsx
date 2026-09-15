import { ChangeEvent, FormEvent, useState, useEffect } from 'react';
import { Camera, Eye, EyeOff, Loader2 } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import SeoMeta from '@/components/SeoMeta';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import AvatarFallback from '../components/AvatarFallback';
import AcademicContextFields from '../components/AcademicContextFields';
import { updateUserProfile, uploadFileObject } from '../lib/client';
import { authApi } from '../lib/auth';
import { showMessage } from '@/lib/messages';
import GoogleSignInButton from '../components/GoogleSignInButton';
import InlineFieldMessage from '../components/InlineFieldMessage';
import { normalizeEmail } from '../lib/normalization';
import {
  buildProfilePictureObjectKey,
  createEmptyProfileForm,
  institutionTypeOptions,
  normalizeOptionalField,
  publicAccountRoleOptions,
  yearOfStudyOptions,
  type ProfileFormValues,
  type PublicAccountRole,
} from '../lib/profile-form';

export default function RegisterPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const returnTo = searchParams.get('returnTo') || '/';
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [accountRole, setAccountRole] = useState<PublicAccountRole>('normal');
  const [profileForm, setProfileForm] = useState<ProfileFormValues>(createEmptyProfileForm());
  const [profileImageFile, setProfileImageFile] = useState<File | null>(null);
  const [profileImagePreview, setProfileImagePreview] = useState<string | null>(null);
  const [profileImageUrlInput, setProfileImageUrlInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { if (error) showMessage({ type: 'error', title: 'Registration failed', message: error }); }, [error]);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const current = await authApi.getCurrentUser();
        if (!cancelled && current) {
          navigate('/resources?sort=-download_count', { replace: true });
        }
      } catch (_) {
        // ignore
      }
    })();
    return () => { cancelled = true; };
  }, [navigate]);
  const passwordStrength = getPasswordStrength(password);
  const hasStartedConfirmingPassword = confirmPassword.length > 0;
  const passwordsMatch = password === confirmPassword;
  const emailError = email.trim() && !/^\S+@\S+\.\S+$/.test(email.trim()) ? 'Enter a valid email address.' : undefined;
  const nameError = !profileForm.display_name.trim() ? 'Full name is required.' : undefined;
  const passwordError = password && password.length < 6 ? 'Password must contain at least 6 characters.' : undefined;
  const confirmError = confirmPassword && !passwordsMatch ? 'Passwords do not match.' : undefined;
  const universityError = profileForm.institution_type !== 'ur_student' && !profileForm.university_name.trim() ? 'University name is required.' : undefined;
  const studentCodeError = profileForm.institution_type === 'ur_student' && !profileForm.ur_student_code.trim() ? 'UR student code is required for UR verification.' : undefined;
  const passwordMatchMessage = hasStartedConfirmingPassword
    ? passwordsMatch
      ? 'Passwords match.'
      : 'Passwords do not match yet.'
    : 'Re-enter your password to confirm it.';

  const updateField = <K extends keyof ProfileFormValues>(field: K, value: ProfileFormValues[K]) => {
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

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (loading) return;
    setLoading(true);
    setError(null);

    const displayName = profileForm.display_name.trim();
    const isUrStudent = profileForm.institution_type === 'ur_student';
    const universityName = profileForm.university_name.trim();
    const urStudentCode = profileForm.ur_student_code.trim();

    if (!displayName) {
      setError('Full name is required.');
      setLoading(false);
      return;
    }

    if (password.length < 6) {
      setError('Password is too weak. Use at least 6 characters.');
      setLoading(false);
      return;
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      setLoading(false);
      return;
    }

    if (isUrStudent && !urStudentCode) {
      setError('UR student code is required if you want UR verification.');
      setLoading(false);
      return;
    }

    if (!isUrStudent && !universityName) {
      setError('University name is required when you select another university.');
      setLoading(false);
      return;
    }

    try {
      await authApi.registerWithCredentials({
        name: displayName,
        email,
        password,
        role: accountRole,
        institution_type: profileForm.institution_type,
        university_name: isUrStudent ? 'University of Rwanda' : universityName,
        ur_student_code: isUrStudent ? urStudentCode : undefined,
        phone_number: normalizeOptionalField(profileForm.phone_number),
        college_name: normalizeOptionalField(profileForm.college_name),
        department_name: normalizeOptionalField(profileForm.department_name),
        institution_id: profileForm.campus_id ? 'ur' : undefined,
        campus_id: normalizeOptionalField(profileForm.campus_id), college_id: normalizeOptionalField(profileForm.college_id), school_id: normalizeOptionalField(profileForm.school_id), programme_id: normalizeOptionalField(profileForm.programme_id),
        programme_name_other: profileForm.programme_id === 'other' ? normalizeOptionalField(profileForm.programme_name_other) : undefined,
        year_of_study: normalizeOptionalField(profileForm.year_of_study),
        bio: normalizeOptionalField(profileForm.bio),
      });

      if (profileImageFile) {
        try {
          const currentUser = await authApi.getCurrentUser();
          if (currentUser?.id) {
            const objectKey = buildProfilePictureObjectKey(currentUser.id, profileImageFile.name);
            const stored = await uploadFileObject('profiles', objectKey, profileImageFile);
            await updateUserProfile({ profile_picture_key: stored.objectKey });
          }
        } catch (uploadError) {
          console.error('Profile image upload failed:', uploadError);
        }
      } else if (profileImageUrlInput.trim()) {
        try {
          const currentUser = await authApi.getCurrentUser();
          if (currentUser?.id) {
            // Save external URL directly as profile_picture_key
            await updateUserProfile({ profile_picture_key: profileImageUrlInput.trim() });
          }
        } catch (uploadError) {
          console.error('Setting profile image URL failed:', uploadError);
        }
      }

      window.location.replace(returnTo);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed, please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="theme-auth-page min-h-screen overflow-hidden px-4 py-8 md:px-8 md:py-10">
      <SeoMeta
        title="Create account"
        description="Private account registration page for UR Academic Resource Hub contributors and students."
        canonicalPath="/register"
        robots="noindex,nofollow"
      />
      <div className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-7xl items-center justify-center gap-6">
        <div className="flex items-center justify-center w-full">
          <div className="theme-auth-card w-full max-w-2xl rounded-[2rem] p-8 md:p-10">
            <div className="mb-8">
              <p className="theme-link-accent mb-3 text-xs font-semibold uppercase tracking-[0.28em]">Join the hub</p>
              <h1 className="theme-title text-3xl font-bold md:text-4xl">Build your student profile</h1>
              <p className="theme-muted mt-3 text-sm leading-6">
                We collect a richer profile so contributors can be identified correctly, verified when needed, and supported with more relevant features.
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
              <div className="theme-soft-panel rounded-2xl p-4">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                  <div className="theme-soft-panel h-24 w-24 overflow-hidden rounded-3xl text-2xl">
                    <AvatarFallback name={profileForm.display_name} imageUrl={profileImagePreview} imageAlt="Profile picture preview" />
                  </div>
                  <div className="flex-1">
                    <Label htmlFor="profile-image" className="theme-form-label">Profile picture</Label>
                    <div className="mt-2">
                      <Input
                        id="profile-image"
                        type="file"
                        accept="image/*"
                        onChange={handleProfileImageChange}
                        className="theme-form-input h-12 rounded-xl cursor-pointer w-full"
                      />
                      <div className="theme-accent-soft mt-2 inline-flex rounded-xl px-3 py-2 text-xs font-medium items-center gap-2">
                        <Camera className="h-4 w-4" />
                        Optional
                      </div>
                    </div>

                    <div className="mt-3 flex items-center gap-2">
                      <Input
                        placeholder="Or paste image URL"
                        value={profileImageUrlInput}
                        onChange={(e) => setProfileImageUrlInput(e.target.value)}
                        className="theme-form-input h-12 rounded-xl flex-1"
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
                      Add a face or logo so your profile is easier to recognize in the community.
                    </p>
                  </div>
                </div>
              </div>

              <div className="grid gap-5 md:grid-cols-2">
                <div className="md:col-span-2">
                  <Label className="theme-form-label">Select role</Label>
                  <Select value={accountRole} onValueChange={(value) => setAccountRole(value as PublicAccountRole)}>
                    <SelectTrigger className="theme-form-input mt-2 h-12 rounded-xl">
                      <SelectValue placeholder="Choose Student, CP, or Lecturer" />
                    </SelectTrigger>
                    <SelectContent>
                      {publicAccountRoleOptions.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="theme-muted mt-2 text-xs">
                    {publicAccountRoleOptions.find((option) => option.value === accountRole)?.description}
                  </p>
                  {accountRole !== 'normal' && (
                    <div className="mt-2 rounded-xl border border-warning-border bg-warning-soft px-3 py-3 text-xs text-warning-foreground">
                      <p className="font-medium">
                        {accountRole === 'cp' ? 'CP access request' : 'Lecturer access request'}
                      </p>
                      <p className="mt-1">
                        After signup, your account will still be created as a normal user first.
                      </p>
                      <p className="mt-1">
                        An admin or content manager must review and approve this request before the {accountRole === 'cp' ? 'CP' : 'Lecturer'} role is granted.
                      </p>
                      <p className="mt-1">
                        Until approval, your uploads and activity will be treated as normal user activity.
                      </p>
                    </div>
                  )}
                </div>

                <div>
                  <Label htmlFor="display_name" className="theme-form-label">Full Name</Label>
                  <Input
                    id="display_name"
                    type="text"
                    value={profileForm.display_name}
                    onChange={(event) => updateField('display_name', event.target.value)}
                    placeholder="Your full name"
                    required
                    className="theme-form-input mt-2 h-12 rounded-xl"
                  />
                  <InlineFieldMessage message={nameError} />
                </div>

                <div>
                  <Label htmlFor="email" className="theme-form-label">Email</Label>
                  <Input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    onBlur={() => setEmail(normalizeEmail(email))}
                    placeholder="you@example.com"
                    required
                    className="theme-form-input mt-2 h-12 rounded-xl"
                  />
                  <InlineFieldMessage message={emailError} />
                </div>

                <div>
                  <Label htmlFor="password" className="theme-form-label">Password</Label>
                  <div className="relative mt-2">
                    <Input
                      id="password"
                      type={showPassword ? 'text' : 'password'}
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      placeholder="Create a password"
                      required
                      minLength={6}
                      className="theme-form-input h-12 rounded-xl pr-12"
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
                  <div className="mt-2 flex items-center justify-between gap-3 text-xs">
                    <p className="theme-muted">Minimum 6 characters</p>
                    <p className={passwordStrength.toneClass}>{passwordStrength.label}</p>
                  </div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-muted">
                    <div className={`${passwordStrength.barClass} h-full rounded-full transition-all`} style={{ width: passwordStrength.width }} />
                  </div>
                  <InlineFieldMessage message={passwordError} />
                </div>

                <div>
                  <Label htmlFor="confirm-password" className="theme-form-label">Confirm Password</Label>
                  <div className="relative mt-2">
                    <Input
                      id="confirm-password"
                      type={showConfirmPassword ? 'text' : 'password'}
                      value={confirmPassword}
                      onChange={(event) => setConfirmPassword(event.target.value)}
                      placeholder="Re-enter your password"
                      required
                      minLength={6}
                      className="theme-form-input h-12 rounded-xl pr-12"
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
                  <p className={`mt-2 text-xs ${hasStartedConfirmingPassword ? (passwordsMatch ? 'text-success-foreground' : 'text-error-foreground') : 'theme-muted'}`}>
                    {passwordMatchMessage}
                  </p>
                  <InlineFieldMessage message={confirmError} />
                </div>

                <div>
                  <Label className="theme-form-label">Student type</Label>
                  <Select
                    value={profileForm.institution_type}
                    onValueChange={(value) => updateField('institution_type', value as ProfileFormValues['institution_type'])}
                  >
                    <SelectTrigger className="theme-form-input mt-2 h-12 rounded-xl">
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
                    type="text"
                    value={profileForm.institution_type === 'ur_student' ? 'University of Rwanda' : profileForm.university_name}
                    onChange={(event) => updateField('university_name', event.target.value)}
                    placeholder="University name"
                    disabled={profileForm.institution_type === 'ur_student'}
                    className="theme-form-input mt-2 h-12 rounded-xl disabled:opacity-80"
                  />
                  <InlineFieldMessage message={universityError} />
                </div>

                <div>
                  <Label htmlFor="ur_student_code" className="theme-form-label">UR Student Code</Label>
                  <Input
                    id="ur_student_code"
                    type="text"
                    value={profileForm.ur_student_code}
                    onChange={(event) => updateField('ur_student_code', event.target.value)}
                    placeholder={profileForm.institution_type === 'ur_student' ? 'Required for UR verification' : 'Not required'}
                    disabled={profileForm.institution_type !== 'ur_student'}
                    className="theme-form-input mt-2 h-12 rounded-xl disabled:opacity-60"
                  />
                  <InlineFieldMessage message={studentCodeError} />
                </div>

                <div>
                  <Label htmlFor="phone_number" className="theme-form-label">Phone Number</Label>
                  <Input
                    id="phone_number"
                    type="tel"
                    value={profileForm.phone_number}
                    onChange={(event) => updateField('phone_number', event.target.value)}
                    placeholder="+250..."
                    className="theme-form-input mt-2 h-12 rounded-xl"
                  />
                </div>

                <div className="sm:col-span-2">
                  <AcademicContextFields value={profileForm} onChange={(academic) => setProfileForm((current) => ({ ...current, ...academic }))} otherName={profileForm.programme_name_other} onOtherNameChange={(programme_name_other) => updateField('programme_name_other', programme_name_other)} submissionSource="registration" />
                </div>

                <div>
                  <Label className="theme-form-label">Year of study</Label>
                  <Select value={profileForm.year_of_study} onValueChange={(value) => updateField('year_of_study', value)}>
                    <SelectTrigger className="theme-form-input mt-2 h-12 rounded-xl">
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
              </div>

              <div>
                <Label htmlFor="bio" className="theme-form-label">Short Bio</Label>
                <Textarea
                  id="bio"
                  value={profileForm.bio}
                  onChange={(event) => updateField('bio', event.target.value)}
                  placeholder="Tell the community what you study or what you like contributing."
                  className="theme-form-input mt-2 min-h-[110px] rounded-2xl"
                />
              </div>

              <div className="theme-warning-note rounded-2xl px-4 py-4 text-sm">
                If you register as a University of Rwanda student, your UR student code is required and your verification status will start as pending until it is reviewed.
              </div>

              {error && <p className="theme-error-note rounded-xl px-4 py-3 text-sm">{error}</p>}

              <Button
                type="submit"
                className="theme-accent-bg h-12 w-full rounded-xl"
                disabled={loading || password.length < 6 || !passwordsMatch}
              >
                {loading ? <span className="flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" />Creating account...</span> : 'Create account'}
              </Button>

              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-border" />
                </div>
                <div className="relative flex justify-center text-xs uppercase tracking-[0.2em] text-muted-foreground">
                  <span className="bg-transparent px-2">or</span>
                </div>
              </div>

              <GoogleSignInButton
                onSuccess={async (credential) => {
                  if (loading) return;
                  setLoading(true);
                  setError(null);
                  try {
                    const token = await authApi.loginWithGoogle(credential);
                    if (token) window.location.replace(returnTo);
                  } catch (err) {
                    setError(err instanceof Error ? err.message : 'Google sign-in failed. Please try again.');
                  } finally {
                    setLoading(false);
                  }
                }}
                onError={(message) => setError(message)}
                disabled={loading}
              />
            </form>

            <div className="theme-auth-subtle mt-6 rounded-2xl px-4 py-4 text-sm">
              <p>
                Already have an account?{' '}
                <button
                  type="button"
                  onClick={() => navigate(`/login?returnTo=${encodeURIComponent(returnTo)}`)}
                  className="theme-link-accent font-semibold underline underline-offset-4"
                >
                  Sign in
                </button>
              </p>
              <p className="theme-muted mt-2 text-xs">
                Your profile details help us verify contributors and build better community trust.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function getPasswordStrength(password: string) {
  if (!password) {
    return {
      label: 'Start typing a password',
      toneClass: 'theme-muted',
      barClass: 'bg-muted-foreground/30',
      width: '0%',
    };
  }

  let score = 0;

  if (password.length >= 6) score += 1;
  if (password.length >= 10) score += 1;
  if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score += 1;
  if (/\d/.test(password)) score += 1;
  if (/[^A-Za-z0-9]/.test(password)) score += 1;

  if (password.length < 6 || score <= 2) {
    return {
      label: 'Weak password',
      toneClass: 'text-error-foreground',
      barClass: 'bg-error',
      width: '33%',
    };
  }

  if (score === 3 || score === 4) {
    return {
      label: 'Medium password',
      toneClass: 'text-warning-foreground',
      barClass: 'bg-warning',
      width: '66%',
    };
  }

  return {
    label: 'Strong password',
    toneClass: 'text-success-foreground',
    barClass: 'bg-success',
    width: '100%',
  };
}
