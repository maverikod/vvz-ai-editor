"""
Shared helpers for driver config tests.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import subprocess
from pathlib import Path

import pytest


def create_dummy_ssl_certs_in_dir(dir_path: Path) -> None:
    """Create minimal valid PEM cert/key in dir_path for file-based validation tests.

    Generates a CA and a server cert signed by that CA so base validator
    (cert chain validation) passes.
    """
    try:
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-keyout",
                str(dir_path / "ca.key"),
                "-out",
                str(dir_path / "ca.crt"),
                "-days",
                "1",
                "-nodes",
                "-subj",
                "/CN=TestCA",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "openssl",
                "req",
                "-new",
                "-newkey",
                "rsa:2048",
                "-keyout",
                str(dir_path / "server.key"),
                "-out",
                str(dir_path / "server.csr"),
                "-nodes",
                "-subj",
                "/CN=localhost",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "openssl",
                "x509",
                "-req",
                "-in",
                str(dir_path / "server.csr"),
                "-CA",
                str(dir_path / "ca.crt"),
                "-CAkey",
                str(dir_path / "ca.key"),
                "-CAcreateserial",
                "-out",
                str(dir_path / "server.crt"),
                "-days",
                "1",
            ],
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        pytest.skip(f"openssl not available or failed: {e}")


def create_crl_for_ca(
    dir_path: Path, ca_cert: str = "ca.crt", ca_key: str = "ca.key"
) -> Path:
    """Create a PEM CRL signed by the test CA in dir_path."""
    from datetime import datetime, timedelta, timezone

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization

    crl_path = dir_path / "ca.crl"
    ca_cert_path = dir_path / ca_cert
    ca_key_path = dir_path / ca_key
    ca = x509.load_pem_x509_certificate(ca_cert_path.read_bytes())
    ca_private_key = serialization.load_pem_private_key(
        ca_key_path.read_bytes(),
        password=None,
    )
    now = datetime.now(timezone.utc)
    crl_builder = (
        x509.CertificateRevocationListBuilder()
        .issuer_name(ca.subject)
        .last_update(now)
        .next_update(now + timedelta(days=1))
    )
    crl = crl_builder.sign(ca_private_key, hashes.SHA256())
    crl_path.write_bytes(crl.public_bytes(serialization.Encoding.PEM))
    return crl_path


def create_mismatched_key_pair(dir_path: Path) -> tuple[Path, Path]:
    """Return cert/key paths where the key does not match the certificate."""
    create_dummy_ssl_certs_in_dir(dir_path)
    other_key = dir_path / "other.key"
    subprocess.run(
        [
            "openssl",
            "req",
            "-new",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(other_key),
            "-out",
            str(dir_path / "other.csr"),
            "-nodes",
            "-subj",
            "/CN=other",
        ],
        check=True,
        capture_output=True,
    )
    return dir_path / "server.crt", other_key
