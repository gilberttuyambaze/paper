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

function normalizeAuthError(error: unknown, fallbackMessage: string): Error {
  if (!axios.isAxiosError(error)) {
    return new Error(fallbackMessage);
  }

  const detail = error.response?.data?.detail;

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

  const rawMessage =
    typeof detail === 'string'
      ? detail
      : typeof error.response?.data?.message === 'string'
        ? error.response.data.message
        : '';
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

  if (rawMessage) {
    return new Error(rawMessage);
  }

  if (error.response?.status === 401) {
    return new Error('Login credentials were not found or are incorrect.');
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

  async requestPasswordReset(email: string): Promise<{ message: string; debug_reset_url?: string | null }> {
    const response = await this.client.post(`${this.getBaseURL()}/api/v1/auth/password-reset/request`, {
      email,
    });

    return {
      message: response.data?.message || 'If an account matches that email, a password reset link has been prepared.',
      debug_reset_url: response.data?.debug_reset_url || null,
    };
  }

  async resetPassword(token: string, password: string): Promise<string> {
    const response = await this.client.post(`${this.getBaseURL()}/api/v1/auth/password-reset/confirm`, {
      token,
      password,
    });
    return response.data?.message || 'Password updated successfully.';
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
