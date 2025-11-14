import base64
import os
from fastapi import FastAPI
from pydantic import BaseModel
from umbral import SecretKey

app = FastAPI()

secret_key = SecretKey.random()
print("Generated Public Key for TEE: " + base64.b64encode(secret_key.public_key().__bytes__()).decode("utf-8"))

def decryptData(ciphertext: bytes) -> bytes:
    plaintext = secret_key.decrypt(ciphertext)
    return plaintext
