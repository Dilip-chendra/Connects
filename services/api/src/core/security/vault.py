"""CredentialVault abstraction providing genuine AES-256-GCM envelope encryption.

Architecture:
1. Ephemeral Data Encryption Key (DEK): A fresh 256-bit (32-byte) key is generated
   via `os.urandom(32)` for every secret.
2. Data Encryption: Plaintext is encrypted with the DEK using AES-256-GCM and a fresh 96-bit nonce.
3. Key Encryption Key (KEK): The master key versioned in environment/KMS wraps the DEK
   using AES-256-GCM with a fresh 96-bit nonce and Authenticated Additional Data (AAD)
   cryptographically binding the secret to tenant_id, connector_id, and key_version.
4. Fail-closed: Decryption fails closed if ciphertext, nonces, DEK, or AAD are tampered with.
5. Key rotation: The `reencrypt` method unwraps the DEK with the source KEK and wraps
   it under the target KEK version without exposing or re-encrypting the payload data.
"""

import os
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class VaultError(Exception):
    """Base exception for all CredentialVault operations."""


class KeyNotFoundError(VaultError):
    """Raised when the requested key version is not configured."""


class DecryptionError(VaultError):
    """Raised when decryption fails due to tampering, wrong key, or invalid AAD."""


@dataclass(frozen=True)
class EnvelopeSecretPayload:
    """Immutable representation of an envelope-encrypted secret payload.
    
    Contains ciphertext encrypted with an ephemeral DEK, and the DEK
    encrypted under the master KEK with AAD binding.
    """

    ciphertext: bytes      # Secret encrypted with ephemeral DEK (includes 16-byte GCM tag)
    data_nonce: bytes      # 12-byte nonce for data encryption
    encrypted_dek: bytes   # 32-byte DEK encrypted with master KEK (includes 16-byte GCM tag)
    dek_nonce: bytes       # 12-byte nonce for DEK encryption
    key_version: str       # Master KEK version (e.g. 'v1', 'v2')
    metadata: dict[str, Any]


# Alias for backwards compatibility
EncryptedSecretPayload = EnvelopeSecretPayload


class CredentialVault:
    """Manages envelope encryption and decryption of third-party credentials.
    
    Uses AES-256-GCM for both data and key-encryption layers with 96-bit random nonces
    and strict AAD binding.
    """

    def __init__(self, keys: dict[str, bytes], active_version: str = "v1") -> None:
        if not keys:
            raise VaultError("CredentialVault requires at least one master key.")
        for ver, key in keys.items():
            if len(key) != 32:
                raise VaultError(
                    f"Key '{ver}' must be exactly 32 bytes (256 bits). Got {len(key)} bytes."
                )
        if active_version not in keys:
            raise KeyNotFoundError(
                f"Active key version '{active_version}' not found in available keys."
            )

        self._keys = keys
        self._active_version = active_version

    @property
    def active_version(self) -> str:
        return self._active_version

    def _build_aad(self, tenant_id: str, connector_id: str, key_version: str) -> bytes:
        """Constructs canonical Authenticated Additional Data (AAD) bytes.
        
        Binds the ciphertext cryptographically to tenant_id, connector_id, and key_version.
        """
        return f"tenant:{tenant_id}|connector:{connector_id}|ver:{key_version}".encode()

    def encrypt(
        self,
        plaintext: str | bytes,
        tenant_id: str,
        connector_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> EnvelopeSecretPayload:
        """Encrypts plaintext using AES-256-GCM envelope encryption.
        
        1. Generates ephemeral 256-bit DEK.
        2. Encrypts plaintext with DEK and data_nonce.
        3. Encrypts DEK with master KEK and dek_nonce, bound to tenant and connector via AAD.
        """
        if not tenant_id or not connector_id:
            raise VaultError("tenant_id and connector_id are required for AAD binding.")

        data = plaintext.encode("utf-8") if isinstance(plaintext, str) else plaintext

        # 1. Generate ephemeral 256-bit Data Encryption Key (DEK)
        dek = os.urandom(32)
        data_nonce = os.urandom(12)

        # 2. Encrypt plaintext with ephemeral DEK (GCM appends 16-byte tag)
        data_cipher = AESGCM(dek)
        ciphertext = data_cipher.encrypt(data_nonce, data, None)

        # 3. Encrypt DEK with master Key Encryption Key (KEK) using AAD
        kek = self._keys[self._active_version]
        kek_cipher = AESGCM(kek)
        dek_nonce = os.urandom(12)
        aad = self._build_aad(tenant_id, connector_id, self._active_version)
        encrypted_dek = kek_cipher.encrypt(dek_nonce, dek, aad)

        return EnvelopeSecretPayload(
            ciphertext=ciphertext,
            data_nonce=data_nonce,
            encrypted_dek=encrypted_dek,
            dek_nonce=dek_nonce,
            key_version=self._active_version,
            metadata=metadata or {},
        )

    def decrypt(
        self,
        payload: EnvelopeSecretPayload,
        tenant_id: str,
        connector_id: str,
    ) -> bytes:
        """Decrypts and authenticates an envelope payload.
        
        1. Decrypts and authenticates DEK using master KEK and AAD.
        2. Decrypts and authenticates plaintext using recovered DEK.
        Fails closed if keys, ciphertext, nonces, or AAD have been modified.
        """
        if payload.key_version not in self._keys:
            raise KeyNotFoundError(
                f"Key version '{payload.key_version}' is not available for decryption."
            )

        kek = self._keys[payload.key_version]
        kek_cipher = AESGCM(kek)
        aad = self._build_aad(tenant_id, connector_id, payload.key_version)

        try:
            # 1. Recover ephemeral DEK from master KEK
            dek = kek_cipher.decrypt(payload.dek_nonce, payload.encrypted_dek, aad)

            # 2. Recover plaintext from ephemeral DEK
            data_cipher = AESGCM(dek)
            plaintext = data_cipher.decrypt(payload.data_nonce, payload.ciphertext, None)
            return plaintext
        except Exception as e:
            # Mask underlying cryptographic details and fail closed
            raise DecryptionError(
                "Decryption failed: integrity verification failed or invalid context."
            ) from e

    def reencrypt(
        self,
        payload: EnvelopeSecretPayload,
        tenant_id: str,
        connector_id: str,
        target_version: str | None = None,
    ) -> EnvelopeSecretPayload:
        """Re-encrypts payload under a new master KEK version.
        
        Demonstrates the core benefit of envelope encryption: unwraps and re-wraps
        only the ephemeral DEK under the target KEK without re-encrypting the data.
        """
        target_ver = target_version or self._active_version
        if target_ver not in self._keys:
            raise KeyNotFoundError(f"Target key version '{target_ver}' is not configured.")

        # 1. Recover DEK under current KEK
        if payload.key_version not in self._keys:
            raise KeyNotFoundError(f"Source key version '{payload.key_version}' is not configured.")

        source_kek = self._keys[payload.key_version]
        source_aad = self._build_aad(tenant_id, connector_id, payload.key_version)

        try:
            dek = AESGCM(source_kek).decrypt(payload.dek_nonce, payload.encrypted_dek, source_aad)
        except Exception as e:
            raise DecryptionError("Failed to unwrap DEK during key rotation.") from e

        # 2. Re-wrap DEK under target KEK
        target_kek = self._keys[target_ver]
        new_dek_nonce = os.urandom(12)
        new_aad = self._build_aad(tenant_id, connector_id, target_ver)
        new_encrypted_dek = AESGCM(target_kek).encrypt(new_dek_nonce, dek, new_aad)

        return EnvelopeSecretPayload(
            ciphertext=payload.ciphertext,  # Data ciphertext is preserved
            data_nonce=payload.data_nonce,
            encrypted_dek=new_encrypted_dek,  # Wrapped under target KEK
            dek_nonce=new_dek_nonce,
            key_version=target_ver,
            metadata=payload.metadata,
        )
