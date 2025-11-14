import os
import json
import base64
from random import shuffle

import requests

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from umbral import (
    SecretKey,
    PublicKey,
    encrypt,
    decrypt_reencrypted,
    CapsuleFrag,
    VerifiedCapsuleFrag,
    VerificationError,
)

STATE_FILE = "./kd/umbral_state.json"


def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("utf-8")


def b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("utf-8"))

def load_state():
    if not os.path.exists(STATE_FILE):
        raise FileNotFoundError(
            f"{STATE_FILE} not found. Generate keys & kfrags first with your keygen script."
        )

    with open(STATE_FILE, "r") as f:
        data = json.load(f)

    master_public_key = PublicKey.from_bytes(b64d(data["master_public_key"]))
    authority_public_key = PublicKey.from_bytes(b64d(data["authority_public_key"]))
    bobs_secret_key = SecretKey.from_bytes(b64d(data["bobs_secret_key"]))
    threshold = data.get("threshold", 4)

    return master_public_key, authority_public_key, bobs_secret_key, threshold


def aes_encrypt(key: bytes, plaintext: bytes, aad: bytes | None = None):
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext, aad)
    return nonce, ct


def aes_decrypt(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes | None = None):
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, aad)


def main():
    (
        master_public_key,
        authority_public_key,
        bobs_secret_key,
        threshold,
    ) = load_state()

    bobs_public_key = bobs_secret_key.public_key()
    authority_verifying_key = authority_public_key

    message = {"message": "Hello, Umbral with AES-GCM!"}
    plaintext = json.dumps(message).encode("utf-8")
    sym_key = os.urandom(32)

    nonce, sym_ciphertext = aes_encrypt(sym_key, plaintext)
    print("Original plaintext:", plaintext)

    capsule, encrypted_sym_key = encrypt(master_public_key, sym_key+nonce)
    assert len(sym_key+nonce) == 44

    capsule_b64 = b64e(bytes(capsule))
    encrypted_sym_key_b64 = b64e(encrypted_sym_key)

    NODE_PORTS = [5000, 5001, 5002, 5003, 5004, 5005, 5006]
    NODE_URL_TEMPLATE = "http://127.0.0.1:{port}/reencrypt"

    verified_cfrags: list[VerifiedCapsuleFrag] = []

    for port in NODE_PORTS:
        url = NODE_URL_TEMPLATE.format(port=port)
        try:
            resp = requests.post(
                url,
                json={
                    "cipherText": encrypted_sym_key_b64,
                    "capsule": capsule_b64,
                },
                timeout=5,
            )
            resp.raise_for_status()
        except Exception:
            continue

        data = resp.json()
        cfrag_b64 = data.get("cFrag")
        if not cfrag_b64:
            continue

        try:
            cfrag_bytes = b64d(cfrag_b64)
        except Exception:
            continue

        try:
            suspicious_cfrag = CapsuleFrag.from_bytes(cfrag_bytes)
        except Exception:
            continue

        try:
            verified_cfrag = suspicious_cfrag.verify(
                capsule=capsule,
                verifying_pk=authority_verifying_key,
                delegating_pk=master_public_key,
                receiving_pk=bobs_public_key,
            )
        except VerificationError:
            continue
        except Exception:
            continue

        verified_cfrags.append(verified_cfrag)

    print(
        f"Collected {len(verified_cfrags)} valid cFrags."
    )

    if len(verified_cfrags) < threshold:
        raise RuntimeError(
            f"Not enough valid cFrags to decrypt symmetric key. "
            f"Needed {threshold}, got {len(verified_cfrags)}."
        )

    shuffle(verified_cfrags)

    recovered_sym_key = decrypt_reencrypted(
        receiving_sk=bobs_secret_key,
        delegating_pk=master_public_key,
        capsule=capsule,
        verified_cfrags=verified_cfrags,
        ciphertext=encrypted_sym_key,
    )

    assert recovered_sym_key == sym_key+nonce, "Recovered AES key does not match original!"

    decrypted_plaintext = aes_decrypt(recovered_sym_key[:32], recovered_sym_key[32:], sym_ciphertext)

    print("Decrypted via AES:", json.loads(decrypted_plaintext.decode("utf-8")))
    assert decrypted_plaintext == plaintext, "Final plaintext mismatch!"


if __name__ == "__main__":
    main()
