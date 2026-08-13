import base64
import hashlib
import logging
import os
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx
from core.config import settings
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError, JWSSignatureError, JWTClaimsError

logger = logging.getLogger(__name__)
FIREBASE_CERTS_URL = "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
GOOGLE_OIDC_ISSUER = "https://accounts.google.com"


def google_oidc_configuration_issue() -> str | None:
    """Return a log-safe Google One Tap configuration diagnosis, never a secret."""
    missing = []
    if not str(getattr(settings, "oidc_client_id", "") or "").strip():
        missing.append("OIDC_CLIENT_ID")
    issuer = str(getattr(settings, "oidc_issuer_url", "") or "").rstrip("/")
    if issuer != GOOGLE_OIDC_ISSUER:
        missing.append("OIDC_ISSUER_URL=https://accounts.google.com")
    return ", ".join(missing) if missing else None


def normalize_firebase_project_id(value: str) -> str:
    normalized = value.strip()
    for suffix in (".firebaseapp.com", ".firebasestorage.app", ".appspot.com", ".web.app"):
        if normalized.lower().endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized


def generate_state() -> str:
    """Generate a secure state parameter for OIDC."""
    return secrets.token_urlsafe(32)


def generate_nonce() -> str:
    """Generate a secure nonce parameter for OIDC."""
    return secrets.token_urlsafe(32)


def generate_code_verifier() -> str:
    """Generate PKCE code verifier."""
    return secrets.token_urlsafe(96)  # 128 bytes base64url encoded


def generate_code_challenge(code_verifier: str) -> str:
    """Generate PKCE code challenge from verifier using SHA256."""
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


async def get_jwks() -> Dict[str, Any]:
    """Get JWKS (JSON Web Key Set) from OIDC provider."""
    metadata = await get_openid_configuration()
    jwks_url = metadata["jwks_uri"]
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            logger.info(f"Fetching JWKS from: {jwks_url}")
            response = await client.get(jwks_url)
            response.raise_for_status()
            jwks_data = response.json()
            logger.info(f"Successfully fetched JWKS with {len(jwks_data.get('keys', []))} keys")
            return jwks_data
    except httpx.TimeoutException as e:
        logger.error(f"Timeout while fetching JWKS from {jwks_url}: {e}")
        raise Exception("Unable to retrieve authentication keys")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error {e.response.status_code} while fetching JWKS from {jwks_url}: {e.response.text}")
        raise Exception("Unable to retrieve authentication keys")
    except Exception as e:
        logger.error(f"Failed to fetch JWKS from {jwks_url}: {e}")
        raise Exception("Unable to retrieve authentication keys")


async def get_openid_configuration() -> Dict[str, Any]:
    issuer = str(settings.oidc_issuer_url).rstrip("/")
    metadata_url = f"{issuer}/.well-known/openid-configuration"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            logger.info("Fetching OIDC metadata from: %s", metadata_url)
            response = await client.get(metadata_url)
            response.raise_for_status()
            metadata = response.json()
    except httpx.TimeoutException as e:
        logger.error("Timeout while fetching OIDC metadata from %s: %s", metadata_url, e)
        raise Exception("Unable to retrieve OIDC provider metadata")
    except httpx.HTTPStatusError as e:
        logger.error("HTTP error %s while fetching OIDC metadata from %s: %s", e.response.status_code, metadata_url, e.response.text)
        raise Exception("Unable to retrieve OIDC provider metadata")
    except Exception as e:
        logger.error("Failed to fetch OIDC metadata from %s: %s", metadata_url, e)
        raise Exception("Unable to retrieve OIDC provider metadata")

    required_keys = ("authorization_endpoint", "token_endpoint", "jwks_uri", "issuer")
    missing = [key for key in required_keys if not metadata.get(key)]
    if missing:
        raise Exception("OIDC provider metadata missing required fields: " + ", ".join(missing))

    return metadata


def get_firebase_project_id() -> str:
    raw_project_id = os.environ.get("FIREBASE_PROJECT_ID") or os.environ.get("VITE_FIREBASE_PROJECT_ID")
    if not raw_project_id:
        raise Exception("Firebase project ID is not configured")
    project_id = normalize_firebase_project_id(raw_project_id)
    if project_id != raw_project_id:
        logger.warning("Normalized Firebase project ID from %s to %s", raw_project_id, project_id)
    return project_id


async def get_firebase_public_keys() -> Dict[str, str]:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            logger.info("Fetching Firebase public keys from: %s", FIREBASE_CERTS_URL)
            response = await client.get(FIREBASE_CERTS_URL)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise Exception("Unexpected Firebase cert payload")
            return payload
    except Exception as e:
        logger.error("Failed to fetch Firebase public keys: %s", e)
        raise Exception("Unable to retrieve Firebase authentication keys")


class IDTokenValidationError(Exception):
    """Custom exception for ID token validation errors."""

    def __init__(self, message: str, error_type: str = "validation_error"):
        self.message = message
        self.error_type = error_type
        super().__init__(self.message)


class AccessTokenError(Exception):
    """Custom exception for application JWT access token errors."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


def hash_password(password: str, iterations: int = 200_000) -> str:
    """Hash a plaintext password for secure storage."""
    if not password:
        raise ValueError("Password is required")

    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored hash."""
    try:
        scheme, iterations, salt_hex, digest_hex = hashed_password.split("$")
        if scheme != "pbkdf2_sha256":
            return False

        salt = bytes.fromhex(salt_hex)
        expected_digest = bytes.fromhex(digest_hex)
        computed_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(iterations),
        )
        return secrets.compare_digest(computed_digest, expected_digest)
    except Exception:
        return False


def create_access_token(claims: Dict[str, Any], expires_minutes: Optional[int] = None) -> str:
    """Create signed JWT access token from provided claims."""
    if not settings.jwt_secret_key:
        logger.error("JWT secret key is not configured")
        raise ValueError("JWT secret key is not configured")

    now = datetime.now(timezone.utc)
    token_claims = claims.copy()

    expiry_minutes = expires_minutes if expires_minutes is not None else int(settings.jwt_expire_minutes)
    expire_at = now + timedelta(minutes=expiry_minutes)

    token_claims.update(
        {
            "exp": expire_at,
            "iat": now,
            "nbf": now,
        }
    )

    token = jwt.encode(token_claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    # Log user hash instead of actual user ID to avoid exposing sensitive information
    user_id = token_claims.get("sub", "unknown")
    user_hash = hashlib.sha256(str(user_id).encode()).hexdigest()[:8] if user_id != "unknown" else "unknown"
    logger.debug("Authentication token created for user hash: %s", user_hash)
    return token


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and validate JWT access token."""
    if not settings.jwt_secret_key:
        logger.error("JWT secret key is not configured")
        raise AccessTokenError("Authentication service is misconfigured")

    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        # Log user hash instead of actual user ID to avoid exposing sensitive information
        user_id = payload.get("sub", "unknown")
        user_hash = hashlib.sha256(str(user_id).encode()).hexdigest()[:8] if user_id != "unknown" else "unknown"
        logger.debug("Authentication token validated for user hash: %s", user_hash)
        return payload
    except ExpiredSignatureError as exc:
        logger.info("Authentication token has expired")
        raise AccessTokenError("Token has expired") from exc
    except JWTError as exc:
        # Log error type only, not the full exception which may contain sensitive token data
        logger.warning("Token validation failed: %s", type(exc).__name__)
        raise AccessTokenError("Invalid authentication token") from exc


async def validate_id_token(id_token: str) -> Optional[Dict[str, Any]]:
    """Validate ID token with proper JWT signature verification using JWKS."""
    config_issue = google_oidc_configuration_issue()
    if config_issue:
        logger.error("Google OIDC configuration incomplete: missing_or_invalid=%s", config_issue)
        raise IDTokenValidationError(
            "Google Sign-In is temporarily unavailable because the server's Google authentication configuration is incomplete.",
            "google_configuration_incomplete",
        )
    try:
        # Get the header to find the key ID
        header = jwt.get_unverified_header(id_token)
        kid = header.get("kid")

        if not kid:
            logger.error("ID token validation failed: No key ID found in JWT header")
            raise IDTokenValidationError("Token format is invalid", "missing_kid")

        # Get JWKS from the provider
        try:
            jwks = await get_jwks()
        except Exception as e:
            logger.error(
                f"ID token validation failed: Failed to fetch JWKS from issuer {settings.oidc_issuer_url}: {e}"
            )
            raise IDTokenValidationError("Unable to retrieve authentication keys", "jwks_fetch_error")

        # Find the matching key
        key = None
        for jwk in jwks.get("keys", []):
            if jwk.get("kid") == kid:
                key = jwk
                break

        if not key:
            logger.error(
                f"ID token validation failed: No key found for kid: {kid} in JWKS from {settings.oidc_issuer_url}"
            )
            raise IDTokenValidationError("Authentication key validation failed", "key_not_found")

        # Convert JWK to PEM format for jose library
        import base64

        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        def base64url_decode(inp):
            """Decode base64url-encoded string."""
            padding = 4 - (len(inp) % 4)
            if padding != 4:
                inp += "=" * padding
            return base64.urlsafe_b64decode(inp)

        try:
            # Extract RSA components
            n = int.from_bytes(base64url_decode(key["n"]), "big")
            e = int.from_bytes(base64url_decode(key["e"]), "big")

            # Construct RSA public key
            public_numbers = rsa.RSAPublicNumbers(e, n)
            public_key = public_numbers.public_key()

            # Convert to PEM format
            pem_key = public_key.public_bytes(
                encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
        except Exception as e:
            logger.error(f"ID token validation failed: Failed to convert JWK to PEM format: {e}")
            raise IDTokenValidationError("Authentication key processing failed", "key_conversion_error")

        # Verify signature and decode the JWT, then validate claims explicitly.
        try:
            metadata = await get_openid_configuration()
            payload = jwt.decode(
                id_token,
                pem_key,
                algorithms=["RS256"],
                options={
                    "verify_aud": False,
                    "verify_iss": False,
                },
            )

            issuer = payload.get("iss")
            allowed_issuers = {metadata["issuer"]}
            if metadata["issuer"] == "https://accounts.google.com":
                allowed_issuers.add("accounts.google.com")
            if issuer not in allowed_issuers:
                logger.error("JWT validation failed: unexpected issuer %s, expected one of %s", issuer, sorted(allowed_issuers))
                raise IDTokenValidationError("Token issuer validation failed", "invalid_issuer")

            audience = payload.get("aud")
            allowed_audience = settings.oidc_client_id
            if isinstance(audience, list):
                audience_valid = allowed_audience in audience
            else:
                audience_valid = audience == allowed_audience
            if not audience_valid:
                logger.error("JWT validation failed: unexpected audience %s, expected %s", audience, allowed_audience)
                raise IDTokenValidationError("Token audience validation failed", "invalid_audience")

            authorized_party = payload.get("azp")
            if isinstance(audience, list) and authorized_party and authorized_party != allowed_audience:
                logger.error("JWT validation failed: unexpected azp %s, expected %s", authorized_party, allowed_audience)
                raise IDTokenValidationError("Token audience validation failed", "invalid_audience")

            # Log user hash instead of actual user ID to avoid exposing sensitive information
            user_id = payload.get("sub", "unknown")
            user_hash = hashlib.sha256(str(user_id).encode()).hexdigest()[:8] if user_id != "unknown" else "unknown"
            logger.info("ID token successfully validated for user hash: %s", user_hash)
            return payload
        except ExpiredSignatureError:
            logger.error("JWT validation failed: ID token has expired")
            raise IDTokenValidationError("Token has expired", "token_expired")
        except JWSSignatureError:
            logger.error("JWT validation failed: Invalid JWT signature")
            raise IDTokenValidationError("Token signature verification failed", "invalid_signature")
        except JWTClaimsError as e:
            # JWTClaimsError covers issuer, audience, and other claims validation
            logger.error(f"JWT validation failed: Claims validation error: {e}")
            if "iss" in str(e).lower() or "issuer" in str(e).lower():
                raise IDTokenValidationError("Token issuer validation failed", "invalid_issuer")
            elif "aud" in str(e).lower() or "audience" in str(e).lower():
                raise IDTokenValidationError("Token audience validation failed", "invalid_audience")
            else:
                raise IDTokenValidationError("Token claims validation failed", "invalid_claims")

    except IDTokenValidationError:
        # Re-raise our custom exceptions
        raise
    except JWTError as e:
        logger.error(f"JWT validation failed: {e}")
        raise IDTokenValidationError("Token validation failed", "jwt_error")
    except Exception as e:
        logger.error(f"Unexpected error during ID token validation: {e}")
        raise IDTokenValidationError("Authentication processing failed", "unexpected_error")


async def validate_firebase_id_token(id_token: str) -> Dict[str, Any]:
    try:
        project_id = get_firebase_project_id()
        header = jwt.get_unverified_header(id_token)
        kid = header.get("kid")
        if not kid:
            raise IDTokenValidationError("Firebase token format is invalid", "missing_kid")

        certs = await get_firebase_public_keys()
        cert = certs.get(kid)
        if not cert:
            logger.error("Firebase token validation failed: no certificate found for kid %s", kid)
            raise IDTokenValidationError("Firebase authentication key validation failed", "key_not_found")

        issuer = f"https://securetoken.google.com/{project_id}"
        payload = jwt.decode(
            id_token,
            cert,
            algorithms=["RS256"],
            audience=project_id,
            issuer=issuer,
        )

        if payload.get("sub") in (None, ""):
            raise IDTokenValidationError("Firebase token subject is missing", "invalid_subject")

        return payload
    except ExpiredSignatureError:
        raise IDTokenValidationError("Firebase token has expired", "token_expired")
    except JWTClaimsError as e:
        logger.error("Firebase token claims validation failed: %s", e)
        if "iss" in str(e).lower() or "issuer" in str(e).lower():
            raise IDTokenValidationError("Firebase token issuer validation failed", "invalid_issuer")
        if "aud" in str(e).lower() or "audience" in str(e).lower():
            raise IDTokenValidationError("Firebase token audience validation failed", "invalid_audience")
        raise IDTokenValidationError("Firebase token claims validation failed", "invalid_claims")
    except JWSSignatureError:
        raise IDTokenValidationError("Firebase token signature verification failed", "invalid_signature")
    except JWTError as e:
        logger.error("Firebase token validation failed: %s", e)
        raise IDTokenValidationError("Firebase token validation failed", "jwt_error")
    except IDTokenValidationError:
        raise
    except Exception as e:
        logger.error("Unexpected error during Firebase token validation: %s", e)
        raise IDTokenValidationError("Firebase authentication processing failed", "unexpected_error")


def build_authorization_url(
    state: str,
    nonce: str,
    code_challenge: Optional[str] = None,
    redirect_uri: Optional[str] = None,
) -> str:
    """Build OIDC authorization URL with optional PKCE support."""
    params = {
        "client_id": settings.oidc_client_id,
        "response_type": "code",
        "scope": getattr(settings, "oidc_scope", "openid email profile"),
        "redirect_uri": redirect_uri or f"{settings.backend_url}/api/v1/auth/callback",
        "state": state,
        "nonce": nonce,
    }

    # Add PKCE parameters if provided
    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"

    issuer = str(settings.oidc_issuer_url).rstrip("/")
    if issuer == "https://accounts.google.com":
        authorization_endpoint = "https://accounts.google.com/o/oauth2/v2/auth"
    else:
        authorization_endpoint = f"{issuer}/authorize"

    auth_url = authorization_endpoint + "?" + urllib.parse.urlencode(params)
    return auth_url


def build_logout_url(id_token: Optional[str] = None) -> str:
    """Build OIDC logout URL."""
    params = {"post_logout_redirect_uri": f"{settings.frontend_url}/logout-callback"}

    if id_token:
        params["id_token_hint"] = id_token

    logout_url = f"{str(settings.oidc_issuer_url).rstrip('/')}/logout?" + urllib.parse.urlencode(params)
    return logout_url
