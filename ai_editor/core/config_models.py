"""
Pydantic models for MCP server configuration (ProjectDir, SVOServiceConfig, ServerConfig).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .constants import (
    DEFAULT_CHUNKER_PORT,
    DEFAULT_LOCALHOST,
    DEFAULT_RETRY_ATTEMPTS,
    DEFAULT_RETRY_DELAY,
)
from .settings_manager import get_settings
from .tls_material_validation import (
    resolve_config_path,
    validate_cert_key_pairing,
    validate_crl_against_ca_or_system,
)


class ProjectDir(BaseModel):
    """Project directory configuration."""

    model_config = {"extra": "forbid"}  # Reject unknown fields

    id: str = Field(..., description="UUID4 identifier")
    name: str = Field(..., description="Human-friendly identifier")
    path: str = Field(..., description="Absolute path to project directory")

    @field_validator("id")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        """Validate UUID4 format."""
        try:
            uuid.UUID(v, version=4)
            return v
        except ValueError:
            raise ValueError(f"Invalid UUID4 format: {v}")

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate absolute path."""
        path = Path(v)
        if not path.is_absolute():
            raise ValueError(f"Path must be absolute: {v}")
        if not path.exists():
            raise ValueError(f"Path does not exist: {v}")
        if not path.is_dir():
            raise ValueError(f"Path must be a directory: {v}")
        return str(path.resolve())


class SVOServiceConfig(BaseModel):
    """Configuration for SVO service integration.

    Each service (chunker, embedding) has its own configuration block with:
    - url: Service URL/hostname
    - port: Service port
    - protocol: Communication protocol (http, https, mtls)
    - Certificate files (if protocol is mtls)
    - Retry configuration for handling service unavailability
    """

    model_config = {"extra": "forbid"}  # Reject unknown fields

    enabled: bool = Field(default=False, description="Enable SVO service")
    url: str = Field(default=DEFAULT_LOCALHOST, description="Service URL or hostname")
    host: str = Field(default=DEFAULT_LOCALHOST, description="Alias for url (host)")
    port: int = Field(default=DEFAULT_CHUNKER_PORT, description="Service port")
    protocol: str = Field(default="http", description="Protocol: http, https, or mtls")
    cert_file: Optional[str] = Field(
        default=None, description="Path to client certificate file (required for mTLS)"
    )
    key_file: Optional[str] = Field(
        default=None, description="Path to client private key file (required for mTLS)"
    )
    ca_cert_file: Optional[str] = Field(
        default=None, description="Path to CA certificate file (required for mTLS)"
    )
    crl_file: Optional[str] = Field(
        default=None, description="Path to CRL file (optional for mTLS)"
    )
    retry_attempts: int = Field(
        default_factory=lambda: get_settings().get(
            "retry_attempts", DEFAULT_RETRY_ATTEMPTS
        ),
        description="Number of retry attempts on failure",
    )
    retry_delay: float = Field(
        default_factory=lambda: get_settings().get("retry_delay", DEFAULT_RETRY_DELAY),
        description="Delay in seconds between retry attempts",
    )
    timeout: Optional[float] = Field(
        default=None, description="Optional timeout for service requests (seconds)"
    )
    check_hostname: bool = Field(
        default=False,
        description="Enable hostname verification for SSL/TLS connections (default: False)",
    )

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, v: str) -> str:
        """Validate protocol value."""
        v_lower = v.lower()
        if v_lower not in ("http", "https", "mtls"):
            raise ValueError(f"Protocol must be 'http', 'https', or 'mtls', got: {v}")
        return v_lower

    @field_validator("cert_file", "key_file", "ca_cert_file", "crl_file")
    @classmethod
    def validate_cert_path(cls, v: Optional[str]) -> Optional[str]:
        """Validate certificate file path exists if provided."""
        if v is None:
            return None
        path = Path(v)
        if not path.exists():
            raise ValueError(f"Certificate file does not exist: {v}")
        return str(path.resolve())

    @model_validator(mode="after")
    def validate_mtls_config(self) -> "SVOServiceConfig":
        """Validate mTLS configuration after initialization."""
        # ``host`` is an alias for ``url``; both default to localhost. Sync only
        # explicitly provided fields so ``url`` in config is not overwritten by
        # the default ``host``.
        fields_set = self.model_fields_set
        url_set = "url" in fields_set
        host_set = "host" in fields_set
        if host_set and not url_set:
            object.__setattr__(self, "url", self.host)
        elif url_set and not host_set:
            object.__setattr__(self, "host", self.url)
        elif host_set and url_set and self.url != self.host:
            object.__setattr__(self, "url", self.host)

        if self.protocol == "mtls":
            if not self.cert_file:
                raise ValueError("cert_file is required when protocol is 'mtls'")
            if not self.key_file:
                raise ValueError("key_file is required when protocol is 'mtls'")
            if not self.ca_cert_file:
                raise ValueError("ca_cert_file is required when protocol is 'mtls'")

        cert_path = (
            resolve_config_path(None, self.cert_file) if self.cert_file else None
        )
        key_path = resolve_config_path(None, self.key_file) if self.key_file else None
        for message in validate_cert_key_pairing(
            cert_path,
            key_path,
            "cert_file",
            "key_file",
        ):
            raise ValueError(message)

        if self.crl_file:
            crl_path = resolve_config_path(None, self.crl_file)
            ca_path = (
                resolve_config_path(None, self.ca_cert_file)
                if self.ca_cert_file
                else None
            )
            if crl_path is not None and crl_path.is_file():
                crl_ok, crl_error = validate_crl_against_ca_or_system(crl_path, ca_path)
                if not crl_ok:
                    raise ValueError(f"crl_file validation failed: {crl_error}")

        return self
