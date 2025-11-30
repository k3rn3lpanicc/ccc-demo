import json
import base64

from umbral import (
    SecretKey,
    Signer,
    generate_kfrags,
    KeyFrag,
    PublicKey
)

STATE_FILE = "umbral_state.json"


def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("utf-8")


def b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("utf-8"))


def save_state(
    master_secret_key: SecretKey,
    authority_signing_key: SecretKey,
    tee_public_key: PublicKey,
    kfrags: list[KeyFrag],
):
    data = {
        "master_public_key": b64e(master_secret_key.public_key().__bytes__()),
        "authority_public_key": b64e(authority_signing_key.public_key().__bytes__()),
        "tee_public_key": b64e(tee_public_key.__bytes__()),
        "kfrags": [b64e(kfrag.__bytes__()) for kfrag in kfrags],
        "threshold": 4,
        "shares": 7,
    }

    with open(STATE_FILE, "w") as f:
        json.dump(data, f, indent=2)


master_secret_key = SecretKey.random()
authority_signing_key = SecretKey.random()

authority_signer = Signer(authority_signing_key)

master_public_key = master_secret_key.public_key()
tee_public_key = PublicKey.from_bytes(
    b64d(input("Please insert TEE's public key (base64): ")))

raw_kfrags = generate_kfrags(
    delegating_sk=master_secret_key,
    receiving_pk=tee_public_key,
    signer=authority_signer,
    threshold=4,
    shares=7,
)

authority_verifying_key = authority_signing_key.public_key()
kfrags = [
    kfrag.kfrag.verify(authority_verifying_key,
                       master_public_key, tee_public_key)
    for kfrag in raw_kfrags
]

save_state(master_secret_key, authority_signing_key, tee_public_key, kfrags)
