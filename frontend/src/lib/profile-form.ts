export type InstitutionType = 'ur_student' | 'other_university';
export type PublicAccountRole = 'normal' | 'cp' | 'lecturer';

export const publicAccountRoleOptions: Array<{
  value: PublicAccountRole;
  label: string;
  description: string;
}> = [
  {
    value: 'normal',
    label: 'student',
    description: 'Use the normal student account for browsing, discussions, downloads, and uploads.',
  },
  {
    value: 'cp',
    label: 'CP',
    description: 'Choose this if you want Class Representative access. This does not grant the role immediately.',
  },
  {
    value: 'lecturer',
    label: 'Lecturer',
    description: 'Choose this if you want Lecturer access. This does not grant the role immediately.',
  },
];

export interface ProfileFormValues {
  display_name: string;
  institution_type: InstitutionType;
  university_name: string;
  ur_student_code: string;
  phone_number: string;
  college_name: string;
  department_name: string;
  institution_id: string;
  campus_id: string;
  college_id: string;
  school_id: string;
  programme_id: string;
  programme_name_other: string;
  year_of_study: string;
  bio: string;
}

export const institutionTypeOptions: Array<{ value: InstitutionType; label: string }> = [
  { value: 'ur_student', label: 'University of Rwanda student' },
  { value: 'other_university', label: 'Other university student' },
];

export const yearOfStudyOptions = [
  'Year 1',
  'Year 2',
  'Year 3',
  'Year 4',
  'Year 5',
  'Postgraduate',
];

export function createEmptyProfileForm(): ProfileFormValues {
  return {
    display_name: '',
    institution_type: 'ur_student',
    university_name: 'University of Rwanda',
    ur_student_code: '',
    phone_number: '',
    college_name: '',
    department_name: '',
    institution_id: 'ur', campus_id: '', college_id: '', school_id: '', programme_id: '', programme_name_other: '',
    year_of_study: '',
    bio: '',
  };
}

export function normalizeOptionalField(value: string): string | undefined {
  const normalized = value.trim();
  return normalized ? normalized : undefined;
}

export function buildProfilePictureObjectKey(userId: string, filename: string): string {
  const extension = filename.includes('.') ? filename.split('.').pop()?.toLowerCase() || 'jpg' : 'jpg';
  return `avatars/${userId}-${Date.now()}.${extension}`;
}
