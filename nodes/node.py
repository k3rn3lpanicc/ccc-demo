import base64
import os
import json
import requests
from fastapi import FastAPI
from pydantic import BaseModel
from umbral import VerifiedKeyFrag, reencrypt, Capsule, CapsuleFrag, PublicKey, VerificationError

KFRAG_B64 = os.getenv("KFRAG")
CORRUPTED = os.getenv("CORRUPTED", "0") == "1"
NODE_PORT = os.getenv("NODE_PORT")

if not KFRAG_B64:
    raise Exception("SECRET_KEY_SHARE and KFRAG must be set in environment")

kfrag_bytes = base64.b64decode(KFRAG_B64)
kfrag = VerifiedKeyFrag.from_verified_bytes(kfrag_bytes)

STATE_FILE = "../kd/umbral_state.json"

app = FastAPI()


def b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("utf-8"))


def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("utf-8")


def load_state():
    if not os.path.exists(STATE_FILE):
        raise FileNotFoundError(f"{STATE_FILE} not found.")

    with open(STATE_FILE, "r") as f:
        data = json.load(f)

    master_public_key = PublicKey.from_bytes(b64d(data["master_public_key"]))
    authority_public_key = PublicKey.from_bytes(
        b64d(data["authority_public_key"]))
    tee_public_key = PublicKey.from_bytes(b64d(data["tee_public_key"]))
    threshold = data.get("threshold", 4)

    return master_public_key, authority_public_key, tee_public_key, threshold


class ReencryptRequest(BaseModel):
    cipherText: str
    capsule: str


@app.post("/reencrypt")
def reencryptData(data: ReencryptRequest):
    if CORRUPTED:
        # Corrupt the kfrag by flipping some bits
        corrupted_bytes = bytearray(kfrag.__bytes__())
        corrupted_bytes[0] ^= 0xFF  # Flip bits in the first byte
        kfrag_corrupted = VerifiedKeyFrag.from_verified_bytes(
            bytes(corrupted_bytes))
        kfrag_to_use = kfrag_corrupted
    else:
        kfrag_to_use = kfrag
    capsule_bytes = base64.b64decode(data.capsule)
    capsule = Capsule.from_bytes(capsule_bytes)
    cfrag = reencrypt(capsule=capsule, kfrag=kfrag_to_use)

    return {
        "cFrag": base64.b64encode(cfrag.__bytes__()).decode()
    }


class UserSubmitVoteRequest(BaseModel):
    encrypted_vote: str
    encrypted_sym_key: str
    capsule: str
    current_state: str


@app.post("/submit_vote")
def submit_vote_via_tee(data: UserSubmitVoteRequest):
    try:
        master_public_key, authority_public_key, tee_public_key, threshold = load_state()

        capsule_b64 = data.capsule
        encrypted_sym_key_b64 = data.encrypted_sym_key

        # Collect cfrags from all nodes
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
                print(f"X Failed to reach node {port}: {e}")
                continue

            node_data = resp.json()
            cfrag_b64 = node_data.get("cFrag")
            if not cfrag_b64:
                print(f"Node {port} did not return 'cFrag' field.")
                continue

            try:
                cfrag_bytes = b64d(cfrag_b64)
            except Exception as e:
                print(f"Node {port} returned invalid base64: {e}")
                continue

            # Verify the cfrag
            try:
                suspicious_cfrag = CapsuleFrag.from_bytes(cfrag_bytes)
            except Exception as e:
                print(f"X Node {port} returned invalid CapsuleFrag: {e}")
                continue

            try:
                capsule_obj = Capsule.from_bytes(b64d(capsule_b64))

                verified_cfrag = suspicious_cfrag.verify(
                    capsule=capsule_obj,
                    verifying_pk=authority_public_key,
                    delegating_pk=master_public_key,
                    receiving_pk=tee_public_key,
                )
                cfrag_b64_list.append(b64e(bytes(verified_cfrag)))
                print(f"Node {port} returned a valid cFrag.")
            except VerificationError as e:
                print(f"Verification failed for node {port}: {e}")
                continue
            except Exception as e:
                print(f"Unexpected error verifying cFrag from {port}: {e}")
                continue

        print(
            f"\nCollected {len(cfrag_b64_list)} valid cFrags (threshold = {threshold}).")

        if len(cfrag_b64_list) < threshold:
            return {
                "success": False,
                "error": f"Not enough valid cFrags. Needed {threshold}, got {len(cfrag_b64_list)}."
            }

        # Call TEE's /submit endpoint
        TEE_URL = "http://127.0.0.1:8000/submit"

        print("\nCalling TEE's /submit endpoint...")
        try:
            resp = requests.post(
                TEE_URL,
                json={
                    "encrypted_vote": data.encrypted_vote,
                    "encrypted_sym_key": encrypted_sym_key_b64,
                    "capsule": capsule_b64,
                    "cfrags": cfrag_b64_list,
                    "current_state": data.current_state,
                },
                timeout=10,
            )
            resp.raise_for_status()

            result = resp.json()
            return result
        except Exception as e:
            print(f"\nFailed to call TEE: {e}")
            return {
                "success": False,
                "error": f"Failed to call TEE: {str(e)}"
            }
    except Exception as e:
        print(f"Decryption process failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }
