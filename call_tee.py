import os
import json
import base64
from random import shuffle

import requests

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from umbral import (
    PublicKey,
    encrypt,
    CapsuleFrag,
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
    bobs_public_key = PublicKey.from_bytes(b64d(data["bobs_public_key"]))
    threshold = data.get("threshold", 4)

    return master_public_key, authority_public_key, bobs_public_key, threshold


def aes_encrypt(key: bytes, plaintext: bytes, aad: bytes | None = None):
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext, aad)
    return nonce, ct


def main():
    (
        master_public_key,
        authority_public_key,
        bobs_public_key,
        threshold,
    ) = load_state()

    authority_verifying_key = authority_public_key

    # Create your message
    message = {"message": "Hello, Umbral with AES-GCM from TEE!"}
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

    # Collect cfrags from nodes
    NODE_PORTS = [5000, 5001, 5002, 5003, 5004, 5005, 5006]
    NODE_URL_TEMPLATE = "http://127.0.0.1:{port}/reencrypt"

    cfrag_b64_list = []

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
        except Exception as e:
            print(f"❌ Failed to reach node {port}: {e}")
            continue

        data = resp.json()
        cfrag_b64 = data.get("cFrag")
        if not cfrag_b64:
            print(f"❌ Node {port} did not return 'cFrag' field.")
            continue

        try:
            cfrag_bytes = b64d(cfrag_b64)
        except Exception as e:
            print(f"❌ Node {port} returned invalid base64: {e}")
            continue

        # Verify the cfrag
        try:
            suspicious_cfrag = CapsuleFrag.from_bytes(cfrag_bytes)
        except Exception as e:
            print(f"❌ Node {port} returned invalid CapsuleFrag: {e}")
            continue

        try:
            # We need to reconstruct capsule for verification
            from umbral import Capsule
            capsule_obj = Capsule.from_bytes(b64d(capsule_b64))
            
            verified_cfrag = suspicious_cfrag.verify(
                capsule=capsule_obj,
                verifying_pk=authority_verifying_key,
                delegating_pk=master_public_key,
                receiving_pk=bobs_public_key,
            )
            # Store the verified cfrag as base64 (we need verified bytes)
            cfrag_b64_list.append(b64e(bytes(verified_cfrag)))
            print(f"✅ Node {port} returned a valid cFrag.")
        except VerificationError as e:
            print(f"❌ Verification failed for node {port}: {e}")
            continue
        except Exception as e:
            print(f"❌ Unexpected error verifying cFrag from {port}: {e}")
            continue

    print(f"\nCollected {len(cfrag_b64_list)} valid cFrags (threshold = {threshold}).")

    if len(cfrag_b64_list) < threshold:
        raise RuntimeError(
            f"Not enough valid cFrags to decrypt. "
            f"Needed {threshold}, got {len(cfrag_b64_list)}."
        )

    # Now call the TEE's /decrypt endpoint
    TEE_URL = "http://127.0.0.1:8000/decrypt"
    
    print("\nCalling TEE's /decrypt endpoint...")
    try:
        resp = requests.post(
            TEE_URL,
            json={
                "encrypted_text": sym_ciphertext_b64,
                "encrypted_sym_key": encrypted_sym_key_b64,
                "capsule": capsule_b64,
                "cfrags": cfrag_b64_list,
            },
            timeout=10,
        )
        resp.raise_for_status()
        
        result = resp.json()
        if result.get("success"):
            print("\n✅ TEE successfully decrypted the message!")
            print(f"Result: {result.get('plaintext')}")
        else:
            print(f"\n❌ TEE decryption failed: {result.get('error')}")
    except Exception as e:
        print(f"\n❌ Failed to call TEE: {e}")


if __name__ == "__main__":
    main()
