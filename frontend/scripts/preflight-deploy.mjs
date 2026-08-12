import fs from 'node:fs';
import path from 'node:path';

const repoRoot = process.cwd();
const envPath = path.join(repoRoot, '.env');
const env = {
  ...readEnvFile(envPath),
  ...process.env,
};

const errors = [];
const warnings = [];

requireValue('DATABASE_URL', 'Backend database connection is required.');
requireValue('JWT_SECRET_KEY', 'JWT signing secret is required.');
requireValue('FRONTEND_URL', 'Frontend URL is required for auth redirects and reset links.');

if (!env.VITE_API_BASE_URL && !env.FRONTEND_API_BASE_URL && !env.PYTHON_BACKEND_URL) {
  warnings.push(
    'No explicit backend URL is configured. That is only safe when the deployed frontend serves /api/config from the same origin.'
  );
}

if (!env.SMTP_HOST || !env.SMTP_FROM_EMAIL) {
  warnings.push(
    'SMTP is not fully configured. Password reset will fall back to log-only delivery unless EXPOSE_PASSWORD_RESET_LINKS is enabled.'
  );
}

if (isTruthy(env.ALLOW_RUNTIME_ENV_MUTATION) && !isTruthy(env.DEBUG)) {
  warnings.push(
    'ALLOW_RUNTIME_ENV_MUTATION is enabled while DEBUG is off. Disable it before production unless you explicitly need runtime env-file edits.'
  );
}

if (errors.length > 0) {
  console.error('Deployment preflight failed:\n');
  for (const error of errors) {
    console.error(`- ${error}`);
  }
  if (warnings.length > 0) {
    console.error('\nWarnings:');
    for (const warning of warnings) {
      console.error(`- ${warning}`);
    }
  }
  process.exit(1);
}

console.log('Deployment preflight passed.');
if (warnings.length > 0) {
  console.log('\nWarnings:');
  for (const warning of warnings) {
    console.log(`- ${warning}`);
  }
}

function requireValue(key, message) {
  if (!env[key] || !String(env[key]).trim()) {
    errors.push(`${key}: ${message}`);
  }
}

function isTruthy(value) {
  return ['1', 'true', 'yes', 'on'].includes(String(value || '').trim().toLowerCase());
}

function readEnvFile(filePath) {
  if (!fs.existsSync(filePath)) {
    return {};
  }

  const result = {};
  const raw = fs.readFileSync(filePath, 'utf8');
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) {
      continue;
    }
    const separator = trimmed.indexOf('=');
    if (separator === -1) {
      continue;
    }
    const key = trimmed.slice(0, separator).trim();
    const value = trimmed.slice(separator + 1).trim();
    result[key] = value;
  }
  return result;
}
