"""Tests for CredentialVault AES-256-GCM genuine envelope encryption."""

import pytest

from src.core.security.vault import (
    CredentialVault,
    DecryptionError,
    EnvelopeSecretPayload,
    KeyNotFoundError,
    VaultError,
)

# 32-byte (256-bit) master test keys (KEKs)
KEY_V1 = b"0123456789abcdef0123456789abcdef"
KEY_V2 = b"fedcba9876543210fedcba9876543210"


@pytest.fixture
def vault() -> CredentialVault:
    return CredentialVault(
        keys={"v1": KEY_V1, "v2": KEY_V2},
        active_version="v1",
    )


def test_vault_initialization_requires_32_byte_keys() -> None:
    with pytest.raises(VaultError, match="must be exactly 32 bytes"):
        CredentialVault(keys={"v1": b"too-short"}, active_version="v1")


def test_vault_roundtrip_envelope_encryption_decryption(vault: CredentialVault) -> None:
    secret = "sk_live_very_secret_token_123456789"
    tenant_id = "tenant-alpha"
    connector_id = "stripe"

    payload = vault.encrypt(secret, tenant_id=tenant_id, connector_id=connector_id)

    assert isinstance(payload, EnvelopeSecretPayload)
    assert payload.key_version == "v1"
    assert len(payload.data_nonce) == 12
    assert len(payload.dek_nonce) == 12
    # 32-byte ephemeral DEK + 16-byte GCM authentication tag = 48 bytes
    assert len(payload.encrypted_dek) == 48
    assert payload.ciphertext != secret.encode()

    decrypted = vault.decrypt(payload, tenant_id=tenant_id, connector_id=connector_id)
    assert decrypted.decode("utf-8") == secret


def test_vault_nonce_uniqueness(vault: CredentialVault) -> None:
    """Verifies that data nonces and DEK nonces are fresh and unique across calls."""
    secret = "static_token"
    data_nonces = set()
    dek_nonces = set()
    for _ in range(500):
        payload = vault.encrypt(secret, tenant_id="t1", connector_id="c1")
        assert payload.data_nonce not in data_nonces
        assert payload.dek_nonce not in dek_nonces
        data_nonces.add(payload.data_nonce)
        dek_nonces.add(payload.dek_nonce)
    assert len(data_nonces) == 500
    assert len(dek_nonces) == 500


def test_vault_tampered_ciphertext_fails(vault: CredentialVault) -> None:
    secret = "secret_to_tamper"
    payload = vault.encrypt(secret, tenant_id="t1", connector_id="c1")

    # Flip the last byte of ciphertext
    tampered_bytes = bytearray(payload.ciphertext)
    tampered_bytes[-1] ^= 0x01
    tampered_payload = EnvelopeSecretPayload(
        ciphertext=bytes(tampered_bytes),
        data_nonce=payload.data_nonce,
        encrypted_dek=payload.encrypted_dek,
        dek_nonce=payload.dek_nonce,
        key_version=payload.key_version,
        metadata=payload.metadata,
    )

    with pytest.raises(DecryptionError):
        vault.decrypt(tampered_payload, tenant_id="t1", connector_id="c1")


def test_vault_tampered_encrypted_dek_fails(vault: CredentialVault) -> None:
    secret = "secret_to_tamper"
    payload = vault.encrypt(secret, tenant_id="t1", connector_id="c1")

    # Tamper with the encrypted DEK
    tampered_dek = bytearray(payload.encrypted_dek)
    tampered_dek[0] ^= 0x01
    tampered_payload = EnvelopeSecretPayload(
        ciphertext=payload.ciphertext,
        data_nonce=payload.data_nonce,
        encrypted_dek=bytes(tampered_dek),
        dek_nonce=payload.dek_nonce,
        key_version=payload.key_version,
        metadata=payload.metadata,
    )

    with pytest.raises(DecryptionError):
        vault.decrypt(tampered_payload, tenant_id="t1", connector_id="c1")


def test_vault_tampered_nonces_fail(vault: CredentialVault) -> None:
    secret = "secret_to_tamper"
    payload = vault.encrypt(secret, tenant_id="t1", connector_id="c1")

    # Tamper with data_nonce
    tampered_dn = bytearray(payload.data_nonce)
    tampered_dn[0] ^= 0x01
    with pytest.raises(DecryptionError):
        vault.decrypt(
            EnvelopeSecretPayload(
                ciphertext=payload.ciphertext,
                data_nonce=bytes(tampered_dn),
                encrypted_dek=payload.encrypted_dek,
                dek_nonce=payload.dek_nonce,
                key_version=payload.key_version,
                metadata=payload.metadata,
            ),
            tenant_id="t1",
            connector_id="c1",
        )

    # Tamper with dek_nonce
    tampered_kn = bytearray(payload.dek_nonce)
    tampered_kn[0] ^= 0x01
    with pytest.raises(DecryptionError):
        vault.decrypt(
            EnvelopeSecretPayload(
                ciphertext=payload.ciphertext,
                data_nonce=payload.data_nonce,
                encrypted_dek=payload.encrypted_dek,
                dek_nonce=bytes(tampered_kn),
                key_version=payload.key_version,
                metadata=payload.metadata,
            ),
            tenant_id="t1",
            connector_id="c1",
        )


def test_vault_cross_tenant_aad_mismatch_fails(vault: CredentialVault) -> None:
    """A secret encrypted for Tenant A cannot be decrypted by Tenant B."""
    secret = "tenant_a_secret"
    payload = vault.encrypt(secret, tenant_id="tenant-A", connector_id="github")

    with pytest.raises(DecryptionError):
        vault.decrypt(payload, tenant_id="tenant-B", connector_id="github")


def test_vault_cross_connector_aad_mismatch_fails(vault: CredentialVault) -> None:
    """A secret bound to GitHub connector cannot be decrypted under Stripe connector."""
    secret = "github_token"
    payload = vault.encrypt(secret, tenant_id="tenant-A", connector_id="github")

    with pytest.raises(DecryptionError):
        vault.decrypt(payload, tenant_id="tenant-A", connector_id="stripe")


def test_vault_missing_key_version_fails(vault: CredentialVault) -> None:
    payload = vault.encrypt("secret", tenant_id="t1", connector_id="c1")
    missing_key_payload = EnvelopeSecretPayload(
        ciphertext=payload.ciphertext,
        data_nonce=payload.data_nonce,
        encrypted_dek=payload.encrypted_dek,
        dek_nonce=payload.dek_nonce,
        key_version="v999",
        metadata=payload.metadata,
    )

    with pytest.raises(KeyNotFoundError):
        vault.decrypt(missing_key_payload, tenant_id="t1", connector_id="c1")


def test_vault_reencryption_key_rotation(vault: CredentialVault) -> None:
    """Verifies that re-encrypting wraps the same DEK under the target KEK version."""
    secret = "rotate_me_safely"
    payload_v1 = vault.encrypt(secret, tenant_id="t1", connector_id="c1")
    assert payload_v1.key_version == "v1"

    # Rotate to v2
    payload_v2 = vault.reencrypt(payload_v1, tenant_id="t1", connector_id="c1", target_version="v2")
    assert payload_v2.key_version == "v2"
    # Core envelope property: underlying ciphertext is untouched
    assert payload_v2.ciphertext == payload_v1.ciphertext
    # Wrapped DEK is re-encrypted with target key
    assert payload_v2.encrypted_dek != payload_v1.encrypted_dek

    # Decrypt with v2 succeeds
    decrypted = vault.decrypt(payload_v2, tenant_id="t1", connector_id="c1")
    assert decrypted.decode("utf-8") == secret
