import os
import json
import base64
from umbral import SecretKey, Capsule, decrypt_original
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

TEE_KEY_FILE = "./tee_secret_key.json"

def b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("utf-8"))

def aes_decrypt(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes | None = None):
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, aad)

def main():
    # Load TEE's secret key
    if not os.path.exists(TEE_KEY_FILE):
        print("❌ TEE key file not found. Start TEE first!")
        return
    
    with open(TEE_KEY_FILE, "r") as f:
        key_data = json.load(f)
        secret_key = SecretKey.from_bytes(base64.b64decode(key_data["secret_key"]))
    
    # Load encrypted state from file
    try:
        with open("contract_state.txt", "r") as f:
            encrypted_state_b64 = f.read().strip()
    except FileNotFoundError:
        print("❌ contract_state.txt not found. Initialize state first!")
        return
    
    # Decrypt the state
    encrypted_bytes = b64d(encrypted_state_b64)
    
    # Format: capsule (98 bytes) + ciphertext (84 bytes) + AES-GCM encrypted state
    capsule_size = 98
    ciphertext_size = 84
    
    capsule_bytes = encrypted_bytes[:capsule_size]
    encrypted_sym_key = encrypted_bytes[capsule_size:capsule_size + ciphertext_size]
    aes_ciphertext = encrypted_bytes[capsule_size + ciphertext_size:]
    
    # Decrypt the symmetric key using TEE's private key
    capsule = Capsule.from_bytes(capsule_bytes)
    sym_key_with_nonce = decrypt_original(secret_key, capsule, encrypted_sym_key)
    
    sym_key = sym_key_with_nonce[:32]
    nonce = sym_key_with_nonce[32:]
    
    # Decrypt the state using AES-GCM
    state_json = aes_decrypt(sym_key, nonce, aes_ciphertext)
    state = json.loads(state_json.decode("utf-8"))
    
    print("\n" + "="*50)
    print("CURRENT BETTING STATE")
    print("="*50)
    print(json.dumps(state, indent=2))
    print("="*50)
    
    if state.get("votes"):
        print(f"\nTotal votes: {len(state['votes'])}")
        print(f"A ratio: {state.get('a_ratio')}")
        
        a_votes = sum(1 for v in state["votes"].values() if v["bet_on"] == "A")
        b_votes = len(state["votes"]) - a_votes
        
        print(f"A votes: {a_votes}")
        print(f"B votes: {b_votes}")
    else:
        print("\nNo votes yet.")


if __name__ == "__main__":
    main()
