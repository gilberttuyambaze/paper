import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]


def _should_load_local_env() -> bool:
    """Avoid loading repo-local secrets in test/CI environments.

    Local developer overrides are still useful in normal runs, but automated tests
    should default to safe, self-contained settings rather than a remote database.
    """
    argv = " ".join(sys.argv).lower()
    if "pytest" in argv or os.getenv("PYTEST_CURRENT_TEST"):
        return False
    environment = (os.getenv("ENVIRONMENT") or "").strip().lower()
    return environment not in {"test", "testing", "ci"}


load_dotenv(BASE_DIR / ".env", override=False)
if _should_load_local_env():
    load_dotenv(BASE_DIR / ".env.local", override=True)


class Settings(BaseSettings):
    # Application
    app_name: str = "FastAPI Modular Template"
    debug: bool = False
    version: str = "1.0.0"
    oidc_scope: str = "openid email profile"
    database_url: str = "sqlite+aiosqlite:///./ur_past_paper.db"
    jwt_secret_key: Optional[str] = None
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    oidc_issuer_url: str = "https://accounts.google.com"
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # AWS Lambda Configuration
    is_lambda: bool = False
    lambda_function_name: str = "fastapi-backend"
    aws_region: str = "us-east-1"

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug(cls, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production", "false", "0", "no", "off"}:
                return False
            if normalized in {"debug", "dev", "development", "true", "1", "yes", "on"}:
                return True
        return value

    @property
    def backend_url(self) -> str:
        """Generate backend URL from host and port."""
        if self.is_lambda:
            # In Lambda environment, return the API Gateway URL
            return os.environ.get(
                "PYTHON_BACKEND_URL", f"https://{self.lambda_function_name}.execute-api.{self.aws_region}.amazonaws.com"
            )
        else:
            # Use localhost for external callbacks instead of 0.0.0.0
            display_host = "127.0.0.1" if self.host == "0.0.0.0" else self.host
            return os.environ.get("PYTHON_BACKEND_URL", f"http://{display_host}:{self.port}")

    @property
    def frontend_url(self) -> str:
        return os.environ.get("FRONTEND_URL", "http://localhost:3000")

    google_drive_enabled: bool = False
    google_drive_folder_id: Optional[str] = None
    google_service_account_json_base64: Optional[str] = None

    # AI is optional. Keep keys server-only; a disabled or unconfigured provider
    # falls back to the local paper-context responder in the study route.
    ai_enabled: bool = False
    ai_provider: str = "groq"
    ai_fallback_provider: Optional[str] = None
    ai_fallback_chain: str = "groq,groq_fallback,gemini,openai,openrouter"

    openai_api_key: Optional[str] = None
    openai_embedding_api_key: Optional[str] = None
    openai_model: str = "gpt-4.1-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_image_model: str = "gpt-image-1"

    groq_api_key: Optional[str] = None
    # A distinct generation-only credential used after GROQ_API_KEY fails.
    groq_fallback_api_key: Optional[str] = None
    groq_model: str = "openai/gpt-oss-120b"

    gemini_api_key: Optional[str] = None
    gemini_embedding_api_key: Optional[str] = None
    gemini_model: str = "gemini-3.6-flash"
    gemini_embedding_model: str = "gemini-embedding-001"

    openrouter_api_key: Optional[str] = None
    openrouter_embedding_api_key: Optional[str] = None
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct"
    openrouter_embedding_model: str = "text-embedding-3-small"

    ai_timeout_seconds: float = 12.0
    ai_max_output_tokens: int = 2048
    study_ai_max_output_tokens: int = 6144
    ai_max_context_tokens: int = 16000
    ai_max_requests_per_user_per_minute: int = 60
    ai_compatible_base_url: Optional[str] = None
    ai_compatible_api_key: Optional[str] = None
    ai_compatible_model: Optional[str] = None
    ai_compatible_embedding_model: Optional[str] = None
    embedding_provider: str = "openrouter"
    embedding_fallback_providers: str = "openai,gemini"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536
    vector_search_top_k: int = 5
    hybrid_search_top_k: int = 40
    rag_context_limit: int = 5

    class Config:
        case_sensitive = False
        extra = "ignore"

    @field_validator("google_drive_enabled", mode="before")
    @classmethod
    def normalize_google_drive_enabled(cls, value: Any) -> bool:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
        return bool(value)

    def __getattr__(self, name: str) -> Any:
        """
        Dynamically read attributes from environment variables.
        For example: settings.opapi_key reads from OPAPI_KEY environment variable.

        Args:
            name: Attribute name (e.g., 'opapi_key')

        Returns:
            Value from environment variable

        Raises:
            AttributeError: If attribute doesn't exist and not found in environment variables
        """
        # Convert attribute name to environment variable name (snake_case -> UPPER_CASE)
        env_var_name = name.upper()

        # Check if environment variable exists
        if env_var_name in os.environ:
            value = os.environ[env_var_name]
            # Cache the value in instance dict to avoid repeated lookups
            self.__dict__[name] = value
            logger.debug(f"Read dynamic attribute {name} from environment variable {env_var_name}")
            return value

        # If not found, raise AttributeError to maintain normal Python behavior
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


# Global settings instance
settings = Settings()
