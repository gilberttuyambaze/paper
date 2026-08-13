# Google Sign-In deployment

Paper Hub uses Google Identity Services One Tap. The browser receives a Google ID
token and posts it to `POST /api/v1/auth/google`; FastAPI validates its issuer,
signature, and audience, finds or creates an application user/profile, and then
issues the existing Paper Hub JWT. Google tokens are never used for normal Paper
Hub API authorization.

## Required configuration

### Render (backend)

- `FRONTEND_URL=https://paperhubur.vercel.app`
- `CORS_ALLOWED_ORIGINS=https://paperhubur.vercel.app`
- `OIDC_ISSUER_URL=https://accounts.google.com`
- `OIDC_CLIENT_ID=<Google Web client ID>`
- `JWT_SECRET_KEY=<application secret>`
- `DATABASE_URL=<Supabase PostgreSQL URL>`

`OIDC_CLIENT_SECRET` is not read by the current One Tap ID-token exchange and
must never be placed in Vercel. Retain it only if a future server-side OAuth
authorization-code flow is implemented.

### Vercel (frontend)

- `VITE_API_BASE_URL=https://ur-hud-backend.onrender.com`
- `VITE_GOOGLE_CLIENT_ID=<the same Google Web client ID as OIDC_CLIENT_ID>`

`VITE_GOOGLE_CLIENT_ID` is public by design. Do not add OIDC client secrets,
JWT secrets, database URLs, Supabase service-role keys, or Google Drive service
account credentials to Vercel frontend variables.

## Google Cloud Console

For the current Google Identity Services One Tap flow, configure the Google Web
OAuth client with these **Authorized JavaScript origins**:

- `http://localhost:3000`
- `http://127.0.0.1:3000` (if used locally)
- `https://paperhubur.vercel.app`

There is **no active FastAPI OAuth redirect/callback route** in the current
Google One Tap implementation, so it requires no Authorized redirect URI. The
repository has a dormant helper that would construct
`<PYTHON_BACKEND_URL>/api/v1/auth/callback`, but no route consumes that URL;
do not register it as a working callback unless a server-side authorization-code
flow and callback route are added together.

## Account behavior

- Existing user with the same stored Google subject: signs in and receives a
  Paper Hub JWT.
- New Google user: a `User` and `UserProfile` are created with normal/default
  roles and normal application authorization rules.
- Existing password account whose email matches a new Google subject: rejected
  with `account_link_required`. The application does not silently merge or
  overwrite identities; explicit account linking is a future feature.
