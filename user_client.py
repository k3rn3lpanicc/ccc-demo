import os
import json
import base64

import requests

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from umbral import (
    PublicKey,
    encrypt,
)

STATE_FILE = "kd/umbral_state.json"


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

    return master_public_key


def aes_encrypt(key: bytes, plaintext: bytes, aad: bytes | None = None):
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext, aad)
    return nonce, ct


def main():
    master_public_key = load_state()

    message = {
        "0xbec8c184a8f55e6443b315361bac3bbb2280e8e8": 1,
        "bet": 100
    }
    plaintext = json.dumps(message).encode("utf-8")
    sym_key = os.urandom(32)

    # AES encrypt the message
    nonce, sym_ciphertext = aes_encrypt(sym_key, plaintext)
    print("Original plaintext:", plaintext)

    # Umbral encrypt the symmetric key + nonce
    capsule, encrypted_sym_key = encrypt(master_public_key, sym_key + nonce)
    assert len(sym_key + nonce) == 44

    capsule_b64 = b64e(bytes(capsule))
    encrypted_sym_key_b64 = b64e(encrypted_sym_key)
    sym_ciphertext_b64 = b64e(sym_ciphertext)

    # Call any node's /submit_vote endpoint (let's use port 5000)
    NODE_URL = "http://127.0.0.1:5000/submit_vote"
    
    print("\nCalling node's /submit_vote endpoint...")
    print("The node will collect cfrags from all nodes and forward to TEE...")
    
    try:
        resp = requests.post(
            NODE_URL,
            json={
                "encrypted_text": sym_ciphertext_b64,
                "encrypted_sym_key": encrypted_sym_key_b64,
                "capsule": capsule_b64,
            },
            timeout=15,
        )
        resp.raise_for_status()
        
        result = resp.json()
        if result.get("success"):
            print("\n✅ Decryption successful!")
            print(f"Result: {result.get('plaintext')}")
        else:
            print(f"\n❌ Decryption failed: {result.get('error')}")
    except Exception as e:
        print(f"\n❌ Failed to call node: {e}")


if __name__ == "__main__":
    main()
