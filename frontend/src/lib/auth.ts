import axios, { AxiosInstance } from 'axios';
import { getAPIBaseURL } from './config';

const TOKEN_KEY = 'ur-hud-auth-token';
const RETURN_TO_KEY = 'ur-hud-return-to';

function isBrowser() {
  return typeof window !== 'undefined';
}

export function getStoredAuthToken(): string | null {
  if (!isBrowser()) return null;

  const token = window.localStorage.getItem(TOKEN_KEY);
  if (!token) return null;

  if (isTokenExpiredOrInvalid(token)) {
    window.localStorage.removeItem(TOKEN_KEY);
    return null;
  }

  return token;
}

export function setStoredAuthToken(token: string) {
  if (!isBrowser()) return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearStoredAuthToken() {
  if (!isBrowser()) return;
  window.localStorage.removeItem(TOKEN_KEY);
}

function setReturnTo(path: string) {
  if (!isBrowser()) return;
  window.sessionStorage.setItem(RETURN_TO_KEY, path);
}

function getReturnTo(): string {
  if (!isBrowser()) return '/';
  return window.sessionStorage.getItem(RETURN_TO_KEY) || '/';
}

function clearReturnTo() {
  if (!isBrowser()) return;
  window.sessionStorage.removeItem(RETURN_TO_KEY);
}

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const [, payload] = token.split('.');
    if (!payload) return null;

    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=');
    const decoded = window.atob(padded);
    return JSON.parse(decoded) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function isTokenExpiredOrInvalid(token: string): boolean {
  const payload = decodeJwtPayload(token);
  if (!payload) {
    return true;
  }

  const exp = payload.exp;
  if (typeof exp !== 'number') {
    return false;
  }

  const now = Math.floor(Date.now() / 1000);
  return exp <= now;
}

export function normalizeAuthError(error: unknown, fallbackMessage: string): Error {
  if (!axios.isAxiosError(error)) {
    const message = error instanceof Error ? error.message.toLowerCase() : '';
    if (message.includes('timeout') || message.includes('aborted')) {
      return new Error('The request timed out. Please try again.');
    }
    return new Error(fallbackMessage);
  }

  const responseData = error.response?.data;
  const detail = responseData?.detail;
  const detailObject = detail && typeof detail === 'object' && !Array.isArray(detail) ? detail : null;
  const code = typeof detailObject?.code === 'string' ? detailObject.code : '';
  const safeDetailMessage = typeof detailObject?.message === 'string' ? detailObject.message : '';

  const knownMessages: Record<string, string> = {
    invalid_credentials: 'Incorrect email or password. Please check your details and try again.',
    email_not_found: 'No account was found with that email address.',
    password_incorrect: 'Incorrect email or password. Please check your details and try again.',
    email_already_registered: 'This email is already registered. Try signing in instead.',
    registration_validation_failed: 'Please review the highlighted account details and try again.',
    account_link_required: 'An account already exists for this email. Sign in with your password to link Google securely.',
    account_suspended: 'Your account is currently suspended. Please contact an administrator.',
    account_disabled: 'Your account is currently disabled. Please contact an administrator.',
    account_pending_approval: 'Your account is pending approval. Please contact an administrator if you need help.',
    google_configuration_incomplete: "Google Sign-In is temporarily unavailable because the server's Google authentication configuration is incomplete.",
    token_expired: 'Google sign-in expired before it could be verified. Please try again.',
    rate_limited: 'Too many requests were made. Please wait a moment and try again.',
  };
  if (code && knownMessages[code]) return new Error(knownMessages[code]);

  if (Array.isArray(detail)) {
    const combinedMessage = detail
      .map((item) => String(item?.msg || ''))
      .join(' ')
      .toLowerCase();

    if (combinedMessage.includes('valid email')) {
      return new Error('Please enter a valid email address.');
    }

    if (combinedMessage.includes('at least 6 characters') || combinedMessage.includes('at least 8 characters')) {
      return new Error('Password is too weak. Use at least 6 characters.');
    }

    return new Error(fallbackMessage);
  }

  const rawMessage = safeDetailMessage || (
    typeof detail === 'string'
      ? detail
      : typeof responseData?.message === 'string'
        ? responseData.message
        : ''
  );
  const message = rawMessage.toLowerCase();

  if (message.includes('already in use') || message.includes('already exists')) {
    return new Error('This email is already in use. Try signing in instead.');
  }

  if (message.includes('no account was found')) {
    return new Error('No account was found with that email address.');
  }

  if (message.includes('valid email')) {
    return new Error('Please enter a valid email address.');
  }

  if (message.includes('password you entered is incorrect') || message.includes('password is incorrect')) {
    return new Error('The password you entered is incorrect.');
  }

  if (message.includes('at least 6 characters') || message.includes('at least 8 characters') || message.includes('too weak')) {
    return new Error('Password is too weak. Use at least 6 characters.');
  }

  if (message.includes('check your email and password') || message.includes('invalid email or password')) {
    return new Error('We could not sign you in. Check your email and password and try again.');
  }

  if (message.includes('ur student code is required')) {
    return new Error('Enter your UR student code to continue with UR verification.');
  }

  if (message.includes('university name is required')) {
    return new Error('Enter your university name to continue.');
  }

  if (rawMessage && error.response && error.response.status < 500) {
    return new Error(rawMessage);
  }

  if (!error.response) {
    if (error.code === 'ECONNABORTED' || error.message.toLowerCase().includes('timeout')) {
      return new Error('The request timed out. Please try again.');
    }
    return new Error('Unable to connect to UR Academic Resource Hub. Please check your internet connection and try again.');
  }

  if (error.response.status === 429) {
    return new Error('Too many requests were made. Please wait a moment and try again.');
  }

  if (error.response.status >= 500) {
    return new Error("We couldn't connect to the server. Please try again in a moment.");
  }

  if (error.response?.status === 401) {
    return new Error('Incorrect email or password. Please check your details and try again.');
  }

  if (error.response?.status === 409) {
    return new Error('This email is already in use. Try signing in instead.');
  }

  return new Error(fallbackMessage);
}

class RPApi {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      withCredentials: true,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.client.interceptors.request.use((config) => {
      const token = getStoredAuthToken();
      if (token) {
        config.headers = {
          ...(config.headers || {}),
          Authorization: `Bearer ${token}`,
        } as any;
      }
      return config;
    });
  }

  private getBaseURL() {
    return getAPIBaseURL();
  }

  async getCurrentUser() {
    const token = getStoredAuthToken();
    if (!token) {
      return null;
    }

    try {
      const response = await this.client.get(`${this.getBaseURL()}/api/v1/auth/me`);
      return response.data;
    } catch (error: any) {
      if (error.response?.status === 401) {
        clearStoredAuthToken();
        return null;
      }
      throw new Error(error.response?.data?.detail || 'Failed to get user info');
    }
  }

  async completePendingFirebaseSignIn(): Promise<string | null> {
    return null;
  }

  async loginWithGoogle(credential: string): Promise<string> {
    try {
      const response = await this.client.post(`${this.getBaseURL()}/api/v1/auth/google`, {
        credential,
      });

      const token = response.data?.token;
      if (!token) {
        throw new Error('Invalid Google login response');
      }

      setStoredAuthToken(token);
      return token;
    } catch (error) {
      throw normalizeAuthError(error, 'Google sign-in failed. Please try again.');
    }
  }

  async login(returnTo?: string) {
    const targetPath =
      returnTo ||
      (isBrowser() ? `${window.location.pathname}${window.location.search}${window.location.hash}` : '/');

    if (isBrowser()) {
      const loginPath = `/login?returnTo=${encodeURIComponent(targetPath)}`;
      window.location.assign(loginPath);
    }
  }

  async register(returnTo?: string) {
    if (isBrowser()) {
      const registerPath = `/register?returnTo=${encodeURIComponent(returnTo || '/')}`;
      window.location.assign(registerPath);
    }
  }

  async loginWithCredentials(email: string, password: string): Promise<string> {
    try {
      const response = await this.client.post(`${this.getBaseURL()}/api/v1/auth/login`, {
        email: email.trim(),
        password,
      });

      const token = response.data?.token;
      if (!token) {
        throw new Error('Invalid login response');
      }

      setStoredAuthToken(token);
      return token;
    } catch (error) {
      throw normalizeAuthError(error, 'Sign in failed. Please try again.');
    }
  }

  async registerWithCredentials(data: {
    name: string;
    email: string;
    password: string;
    role: 'normal' | 'cp' | 'lecturer';
    institution_type: 'ur_student' | 'other_university';
    university_name?: string;
    ur_student_code?: string;
    phone_number?: string;
    college_name?: string;
    department_name?: string;
    institution_id?: string;
    campus_id?: string;
    college_id?: string;
    school_id?: string;
    programme_id?: string;
    programme_name_other?: string;
    year_of_study?: string;
    bio?: string;
  }): Promise<string> {
    try {
      const response = await this.client.post(`${this.getBaseURL()}/api/v1/auth/register`, {
        ...data,
        email: data.email.trim(),
      });

      const token = response.data?.token;
      if (!token) {
        throw new Error('Invalid registration response');
      }

      setStoredAuthToken(token);
      return token;
    } catch (error) {
      throw normalizeAuthError(error, 'Account creation failed. Please try again.');
    }
  }

  async setPassword(password: string): Promise<string> {
    try {
      const response = await this.client.post(`${this.getBaseURL()}/api/v1/auth/password`, {
        password,
      });

      return response.data?.message || 'Password updated successfully.';
    } catch (error) {
      throw normalizeAuthError(error, 'Unable to update password right now. Please try again.');
    }
  }

  async requestPasswordReset(email: string): Promise<{ message: string; debug_reset_url?: string | null }> {
    try {
      const response = await this.client.post(`${this.getBaseURL()}/api/v1/auth/password-reset/request`, {
        email,
      });

      return {
        message: response.data?.message || 'If an account matches that email, a password reset link has been prepared.',
        debug_reset_url: response.data?.debug_reset_url || null,
      };
    } catch (error) {
      throw normalizeAuthError(error, 'Unable to send reset instructions right now. Please try again.');
    }
  }

  async resetPassword(token: string, password: string): Promise<string> {
    try {
      const response = await this.client.post(`${this.getBaseURL()}/api/v1/auth/password-reset/confirm`, {
        token,
        password,
      });
      return response.data?.message || 'Password updated successfully.';
    } catch (error) {
      throw normalizeAuthError(error, 'Unable to reset your password right now. Request a new link and try again.');
    }
  }

  async completeLoginCallback(): Promise<string> {
    return '/';
  }

  async logout() {
    try {
      clearStoredAuthToken();
      clearReturnTo();
      if (isBrowser()) {
        const response = await this.client.get(`${this.getBaseURL()}/api/v1/auth/logout`);
        window.location.assign(response.data?.redirect_url || '/');
      }
    } catch (error: any) {
      clearStoredAuthToken();
      clearReturnTo();
      if (isBrowser()) window.location.assign('/');
      throw new Error(error?.response?.data?.detail || error?.message || 'Failed to logout');
    }
  }
}

export const authApi = new RPApi();
