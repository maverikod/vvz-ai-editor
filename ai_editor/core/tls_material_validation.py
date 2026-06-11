"""
TLS certificate material validation (cert/key pairing, CRL issuer).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
import ssl
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import dsa, ec, padding, rsa

try:
    from mcp_proxy_adapter.core.certificate.certificate_validator import (
        CertificateValidator,
    )
except ImportError:  # pragma: no cover - optional at import time in minimal envs
    CertificateValidator = None  # type: ignore[misc, assignment]

_PEM_CERT_RE = re.compile(
    rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
    re.DOTALL,
)


@dataclass(frozen=True)
class TlsMaterialBlock:
    """Normalized TLS file paths for one config section."""

    section: str
    key_prefix: str
    cert: Optional[str]
    key: Optional[str]
    ca: Optional[str]
    crl: Optional[str]
    protocol: Optional[str] = None


def resolve_config_path(
    config_dir: Optional[Path], path_value: Optional[str]
) -> Optional[Path]:
    """Resolve a config path relative to the config file directory."""
    if not path_value or not isinstance(path_value, str) or not path_value.strip():
        return None
    file_path = Path(path_value)
    if not file_path.is_absolute() and config_dir is not None:
        file_path = config_dir / file_path
    return file_path


def _non_empty(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _block_from_ssl_dict(
    section: str,
    key_prefix: str,
    ssl_dict: Dict[str, Any],
    protocol: Optional[str],
) -> Optional[TlsMaterialBlock]:
    cert = _non_empty(ssl_dict.get("cert"))
    key = _non_empty(ssl_dict.get("key"))
    ca = _non_empty(ssl_dict.get("ca"))
    crl = _non_empty(ssl_dict.get("crl"))
    if not any((cert, key, ca, crl)):
        return None
    return TlsMaterialBlock(
        section=section,
        key_prefix=key_prefix,
        cert=cert,
        key=key,
        ca=ca,
        crl=crl,
        protocol=protocol,
    )


def _block_from_flat_dict(
    section: str,
    key_prefix: str,
    block: Dict[str, Any],
    protocol: Optional[str],
) -> Optional[TlsMaterialBlock]:
    cert = _non_empty(block.get("cert_file"))
    key = _non_empty(block.get("key_file"))
    ca = _non_empty(block.get("ca_cert_file"))
    crl = _non_empty(block.get("crl_file"))
    if not any((cert, key, ca, crl)):
        return None
    return TlsMaterialBlock(
        section=section,
        key_prefix=key_prefix,
        cert=cert,
        key=key,
        ca=ca,
        crl=crl,
        protocol=protocol,
    )


def iter_tls_material_blocks(config_data: Dict[str, Any]) -> Iterator[TlsMaterialBlock]:
    """Yield every config block that references TLS certificate material."""
    for section_name in ("server", "client", "registration", "server_validation"):
        section = config_data.get(section_name)
        if not isinstance(section, dict):
            continue
        ssl_dict = section.get("ssl")
        if isinstance(ssl_dict, dict):
            block = _block_from_ssl_dict(
                section_name,
                "ssl.",
                ssl_dict,
                _non_empty(section.get("protocol")),
            )
            if block is not None:
                yield block

    ai_editor = config_data.get("ai_editor")
    if isinstance(ai_editor, dict):
        for service_name in ("chunker", "embedding"):
            service = ai_editor.get(service_name)
            if isinstance(service, dict):
                block = _block_from_flat_dict(
                    "ai_editor",
                    f"{service_name}.",
                    service,
                    _non_empty(service.get("protocol")),
                )
                if block is not None:
                    yield block


def _load_pem_certificate(path: Path) -> x509.Certificate:
    return x509.load_pem_x509_certificate(path.read_bytes())


def _load_crl(path: Path) -> x509.CertificateRevocationList:
    data = path.read_bytes()
    try:
        return x509.load_pem_x509_crl(data)
    except ValueError:
        return x509.load_der_x509_crl(data)


def _iter_pem_certificates_from_file(path: Path) -> Iterator[x509.Certificate]:
    if not path.is_file():
        return
    for match in _PEM_CERT_RE.finditer(path.read_bytes()):
        yield x509.load_pem_x509_certificate(match.group(0))


def _iter_system_trust_store_paths() -> List[Path]:
    paths: List[Path] = []
    seen: set[str] = set()
    defaults = ssl.get_default_verify_paths()
    for candidate in (
        defaults.cafile,
        defaults.capath,
        defaults.openssl_cafile,
        defaults.openssl_capath,
    ):
        if not candidate:
            continue
        resolved = str(Path(candidate).resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        paths.append(Path(candidate))
    try:
        import certifi

        certifi_path = Path(certifi.where()).resolve()
        if str(certifi_path) not in seen:
            seen.add(str(certifi_path))
            paths.append(certifi_path)
    except ImportError:
        pass
    return paths


def _verify_crl_signature(
    crl: x509.CertificateRevocationList,
    issuer: x509.Certificate,
) -> bool:
    public_key = issuer.public_key()
    hash_alg = crl.signature_hash_algorithm
    if hash_alg is None:
        return False
    try:
        if isinstance(public_key, rsa.RSAPublicKey):
            public_key.verify(
                crl.signature,
                crl.tbs_certlist_bytes,
                padding.PKCS1v15(),
                hash_alg,
            )
        elif isinstance(public_key, ec.EllipticCurvePublicKey):
            public_key.verify(
                crl.signature,
                crl.tbs_certlist_bytes,
                ec.ECDSA(hash_alg),
            )
        elif isinstance(public_key, dsa.DSAPublicKey):
            public_key.verify(
                crl.signature,
                crl.tbs_certlist_bytes,
                hash_alg,
            )
        else:
            return False
        return True
    except InvalidSignature:
        return False
    except (TypeError, ValueError):
        return False


def _crl_verified_by_ca(
    crl: x509.CertificateRevocationList,
    ca_cert: x509.Certificate,
) -> bool:
    if crl.issuer != ca_cert.subject:
        return False
    return _verify_crl_signature(crl, ca_cert)


def validate_crl_against_ca_or_system(
    crl_path: Path,
    ca_path: Optional[Path],
) -> Tuple[bool, Optional[str]]:
    """
    Verify CRL signature against configured CA or system trust store.

    Returns:
        (is_valid, error_message)
    """
    try:
        crl = _load_crl(crl_path)
    except (ValueError, OSError) as exc:
        return False, f"failed to load CRL: {exc}"

    if ca_path is not None and ca_path.is_file():
        try:
            ca_cert = _load_pem_certificate(ca_path)
        except (ValueError, OSError) as exc:
            return False, f"failed to load CA certificate: {exc}"
        if _crl_verified_by_ca(crl, ca_cert):
            return True, None
        return False, "CRL is not signed by the configured CA certificate"

    for store_path in _iter_system_trust_store_paths():
        if store_path.is_dir():
            for ca_file in store_path.glob("*.pem"):
                for ca_cert in _iter_pem_certificates_from_file(ca_file):
                    if _crl_verified_by_ca(crl, ca_cert):
                        return True, None
            for ca_file in store_path.glob("*.crt"):
                for ca_cert in _iter_pem_certificates_from_file(ca_file):
                    if _crl_verified_by_ca(crl, ca_cert):
                        return True, None
            continue
        if not store_path.is_file():
            continue
        for ca_cert in _iter_pem_certificates_from_file(store_path):
            if _crl_verified_by_ca(crl, ca_cert):
                return True, None

    return False, "CRL is not signed by any configured or system trust-anchor CA"


def validate_cert_key_pairing(
    cert_path: Optional[Path],
    key_path: Optional[Path],
    cert_label: str,
    key_label: str,
) -> List[str]:
    """Return error messages for cert/key pairing and match checks."""
    errors: List[str] = []
    cert_set = cert_path is not None and cert_path.is_file()
    key_set = key_path is not None and key_path.is_file()

    if cert_set and not key_set:
        errors.append(f"{cert_label} is set but {key_label} is missing")
    elif key_set and not cert_set:
        errors.append(f"{key_label} is set but {cert_label} is missing")
    elif cert_set and key_set and CertificateValidator is not None:
        if not CertificateValidator.validate_certificate_key_match(
            str(cert_path),
            str(key_path),
        ):
            errors.append(f"{cert_label} does not match {key_label}")
    return errors


def _field_names(block: TlsMaterialBlock) -> Tuple[str, str, str]:
    """Return (cert_field, key_field, crl_field) config keys for error reporting."""
    if block.key_prefix in ("chunker.", "embedding."):
        return (
            f"{block.key_prefix}cert_file",
            f"{block.key_prefix}key_file",
            f"{block.key_prefix}crl_file",
        )
    return (
        f"{block.key_prefix}cert",
        f"{block.key_prefix}key",
        f"{block.key_prefix}crl",
    )


def validate_tls_material_block(
    block: TlsMaterialBlock,
    config_dir: Optional[Path],
) -> List[Tuple[str, str, Optional[str]]]:
    """
    Validate one TLS block.

    Returns:
        List of (level, message, key_suffix) tuples.
    """
    findings: List[Tuple[str, str, Optional[str]]] = []
    cert_path = resolve_config_path(config_dir, block.cert)
    key_path = resolve_config_path(config_dir, block.key)
    ca_path = resolve_config_path(config_dir, block.ca)
    crl_path = resolve_config_path(config_dir, block.crl)

    cert_field, key_field, crl_field = _field_names(block)
    cert_label = f"{block.section}.{cert_field}"
    key_label = f"{block.section}.{key_field}"

    for message in validate_cert_key_pairing(
        cert_path, key_path, cert_label, key_label
    ):
        if f"{key_label} is missing" in message:
            findings.append(("error", message, key_field))
        elif f"{cert_label} is missing" in message:
            findings.append(("error", message, cert_field))
        else:
            findings.append(("error", message, cert_field))

    if crl_path is not None and crl_path.is_file():
        crl_valid, crl_error = validate_crl_against_ca_or_system(crl_path, ca_path)
        if not crl_valid:
            findings.append(
                (
                    "error",
                    f"CRL validation failed for {block.section}.{crl_field}: {crl_error}",
                    crl_field,
                )
            )
        elif (
            CertificateValidator is not None
            and cert_path is not None
            and cert_path.is_file()
            and block.crl
            and not CertificateValidator.validate_certificate_not_revoked(
                str(cert_path),
                str(crl_path),
            )
        ):
            findings.append(
                (
                    "error",
                    f"{cert_label} is revoked according to {block.section}.{crl_field}",
                    crl_field,
                )
            )

    return findings
