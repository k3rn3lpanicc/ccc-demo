import base64
import os
import json
from fastapi import FastAPI
from pydantic import BaseModel
from umbral import SecretKey, PublicKey, decrypt_reencrypted, Capsule, VerifiedCapsuleFrag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

STATE_FILE = "./kd/umbral_state.json"

app = FastAPI()

secret_key = SecretKey.random()
print("TEE Public Key: " + base64.b64encode(secret_key.public_key().__bytes__()).decode("utf-8"))

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

def aes_decrypt(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes | None = None):
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, aad)

def decryptData(ciphertext: bytes) -> bytes:
    plaintext = secret_key.decrypt(ciphertext)
    return plaintext

class DecryptRequest(BaseModel):
    encrypted_text: str
    encrypted_sym_key: str
    capsule: str
    cfrags: list[str]

@app.post("/submit")
def decrypt_and_print(data: DecryptRequest):
    try:
        master_public_key = load_state()
        
        sym_ciphertext = b64d(data.encrypted_text)
        encrypted_sym_key = b64d(data.encrypted_sym_key)
        capsule = Capsule.from_bytes(b64d(data.capsule))
        
        verified_cfrags = []
        for cfrag_b64 in data.cfrags:
            cfrag_bytes = b64d(cfrag_b64)
            verified_cfrag = VerifiedCapsuleFrag.from_verified_bytes(cfrag_bytes)
            verified_cfrags.append(verified_cfrag)
        
        recovered_sym_key = decrypt_reencrypted(
            receiving_sk=secret_key,
            delegating_pk=master_public_key,
            capsule=capsule,
            verified_cfrags=verified_cfrags,
            ciphertext=encrypted_sym_key,
        )
        
        sym_key = recovered_sym_key[:32]
        nonce = recovered_sym_key[32:]
        
        decrypted_plaintext = aes_decrypt(sym_key, nonce, sym_ciphertext)
        
        try:
            result = json.loads(decrypted_plaintext.decode("utf-8"))
        except:
            result = decrypted_plaintext.decode("utf-8")
        
        print("Decrypted plaintext:", result)
        
        return {
            "success": True,
            "plaintext": result
        }
    except Exception as e:
        print(f"Decryption failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }
