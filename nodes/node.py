import base64
import os
from fastapi import FastAPI
from pydantic import BaseModel
from umbral import VerifiedKeyFrag, reencrypt, Capsule

KFRAG_B64 = os.getenv("KFRAG")
CORRUPTED = os.getenv("CORRUPTED", "0") == "1"
if not KFRAG_B64:
    raise Exception("SECRET_KEY_SHARE and KFRAG must be set in environment")


kfrag_bytes = base64.b64decode(KFRAG_B64)
kfrag = VerifiedKeyFrag.from_verified_bytes(kfrag_bytes)

app = FastAPI()

class ReencryptRequest(BaseModel):
    cipherText: str
    capsule: str

@app.post("/reencrypt")
def reencryptData(data: ReencryptRequest):
    if CORRUPTED:
        # Corrupt the kfrag by flipping some bits
        corrupted_bytes = bytearray(kfrag.__bytes__())
        corrupted_bytes[0] ^= 0xFF  # Flip bits in the first byte
        kfrag_corrupted = VerifiedKeyFrag.from_verified_bytes(bytes(corrupted_bytes))
        kfrag_to_use = kfrag_corrupted
    else:
        kfrag_to_use = kfrag
    capsule_bytes = base64.b64decode(data.capsule)
    capsule = Capsule.from_bytes(capsule_bytes)
    cfrag = reencrypt(capsule=capsule, kfrag=kfrag_to_use)

    return {
        "cFrag": base64.b64encode(cfrag.__bytes__()).decode()
    }
