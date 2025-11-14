import os
import json
import base64
from random import shuffle

from umbral import (
    decrypt_reencrypted,
    SecretKey,
    Signer,
    encrypt,
    generate_kfrags,
    reencrypt,
    KeyFrag,
    VerifiedKeyFrag
)

STATE_FILE = "umbral_state.json"


def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("utf-8")


def b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("utf-8"))


def save_state(
    master_secret_key: SecretKey,
    authority_signing_key: SecretKey,
    bobs_secret_key: SecretKey,
    kfrags: list[KeyFrag],
):
    data = {
        "master_public_key": b64e(master_secret_key.public_key().__bytes__()),
        "authority_public_key": b64e(authority_signing_key.public_key().__bytes__()),
        "bobs_secret_key": b64e(bobs_secret_key.to_secret_bytes()),
        "kfrags": [b64e(kfrag.__bytes__()) for kfrag in kfrags],
        "threshold": 4,
        "shares": 7,
    }

    with open(STATE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_state():
    with open(STATE_FILE, "r") as f:
        data = json.load(f)
    print(data["master_secret_key"])
    master_secret_key = SecretKey.from_bytes(b64d(data["master_secret_key"]))
    authority_signing_key = SecretKey.from_bytes(b64d(data["authority_signing_key"]))
    bobs_secret_key = SecretKey.from_bytes(b64d(data["bobs_secret_key"]))
    kfrags = [VerifiedKeyFrag.from_verified_bytes(b64d(kf_b64)) for kf_b64 in data["kfrags"]]

    return master_secret_key, authority_signing_key, bobs_secret_key, kfrags


# -------------------------------------------------
# Load or create keys + kfrags
# -------------------------------------------------
if os.path.exists(STATE_FILE):
    print(f"Loading keys and kfrags from {STATE_FILE}...")
    (
        master_secret_key,
        authority_signing_key,
        bobs_secret_key,
        kfrags,
    ) = load_state()
else:
    print("No state file found. Generating new keys and kfrags...")

    master_secret_key = SecretKey.random()
    authority_signing_key = SecretKey.random()
    bobs_secret_key = SecretKey.random()

    authority_signer = Signer(authority_signing_key)

    master_public_key = master_secret_key.public_key()
    bobs_public_key = bobs_secret_key.public_key()

    raw_kfrags = generate_kfrags(
        delegating_sk=master_secret_key,
        receiving_pk=bobs_public_key,
        signer=authority_signer,
        threshold=4,
        shares=7,
    )

    authority_verifying_key = authority_signing_key.public_key()
    kfrags = [
        kfrag.kfrag.verify(authority_verifying_key, master_public_key, bobs_public_key)
        for kfrag in raw_kfrags
    ]

    save_state(master_secret_key, authority_signing_key, bobs_secret_key, kfrags)
    print(f"Saved keys and kfrags to {STATE_FILE}.")

# -------------------------------------------------
# Use loaded/generated material as normal
# -------------------------------------------------
master_public_key = master_secret_key.public_key()
bobs_public_key = bobs_secret_key.public_key()
authority_signer = Signer(authority_signing_key)
authority_verifying_key = authority_signing_key.public_key()

plaintext = b"Proxy Re-Encryption is cool!"
capsule, ciphertext = encrypt(master_public_key, plaintext)

cfrags = []
for kfrag in kfrags[1:5]:
    cfrag = reencrypt(capsule=capsule, kfrag=kfrag)
    cfrags.append(cfrag)

shuffle(cfrags)

bob_cleartext = decrypt_reencrypted(
    receiving_sk=bobs_secret_key,
    delegating_pk=master_public_key,
    capsule=capsule,
    verified_cfrags=cfrags,
    ciphertext=ciphertext,
)

assert bob_cleartext == plaintext
