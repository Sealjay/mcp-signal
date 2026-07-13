from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac as hmac_mod
import os
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from mcp_signal.server import build_server


def test_decrypt_attachment_success(tmp_path):
    """Decrypt a valid encrypted attachment."""
    plaintext = b"hello world" + b"\x05\x05\x05\x05\x05"  # PKCS7 pad to 16-byte boundary
    cipher_key = os.urandom(32)
    mac_key = os.urandom(32)
    local_key = base64.b64encode(cipher_key + mac_key).decode()

    iv = os.urandom(16)
    cipher = Cipher(
        algorithms.AES(cipher_key),
        modes.CBC(iv),
        backend=default_backend(),
    )
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(plaintext) + encryptor.finalize()

    hmac_digest = hmac_mod.new(mac_key, iv + ciphertext, hashlib.sha256).digest()

    encrypted_file = tmp_path / "encrypted.bin"
    encrypted_file.write_bytes(iv + ciphertext + hmac_digest)

    server = build_server()
    tool_result = asyncio.run(
        server.call_tool(
            "decrypt_attachment",
            {
                "encrypted_path": str(encrypted_file),
                "local_key": local_key,
            },
        )
    )

    result = tool_result.structured_content["result"]
    assert isinstance(result, str)
    assert not result.startswith("Error:"), f"Got error: {result}"

    decrypted_path = Path(result)
    assert decrypted_path.exists()
    assert decrypted_path.read_bytes() == b"hello world"


def test_decrypt_attachment_hmac_tamper(tmp_path):
    """Tampered HMAC should fail verification."""
    plaintext = b"hello world" + b"\x05\x05\x05\x05\x05"
    cipher_key = os.urandom(32)
    mac_key = os.urandom(32)
    local_key = base64.b64encode(cipher_key + mac_key).decode()

    iv = os.urandom(16)
    cipher = Cipher(
        algorithms.AES(cipher_key),
        modes.CBC(iv),
        backend=default_backend(),
    )
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(plaintext) + encryptor.finalize()

    hmac_digest = hmac_mod.new(mac_key, iv + ciphertext, hashlib.sha256).digest()
    hmac_digest_tampered = bytearray(hmac_digest)
    hmac_digest_tampered[0] ^= 0xFF
    hmac_digest_tampered = bytes(hmac_digest_tampered)

    encrypted_file = tmp_path / "encrypted.bin"
    encrypted_file.write_bytes(iv + ciphertext + hmac_digest_tampered)

    server = build_server()
    tool_result = asyncio.run(
        server.call_tool(
            "decrypt_attachment",
            {
                "encrypted_path": str(encrypted_file),
                "local_key": local_key,
            },
        )
    )

    result = tool_result.structured_content["result"]
    assert result == "Error: HMAC verification failed"
