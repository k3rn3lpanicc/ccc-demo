import os 
import json 
import base64 
from random import shuffle 
import requests 
from umbral import ( SecretKey, encrypt, decrypt_reencrypted, CapsuleFrag, VerifiedCapsuleFrag, VerificationError, PublicKey ) 
STATE_FILE = "./kd/umbral_state.json" 

def b64e(b: bytes) -> str: 
    return base64.b64encode(b).decode("utf-8") 
def b64d(s: str) -> bytes: 
    return base64.b64decode(s.encode("utf-8")) 

def load_state(): 
    if not os.path.exists(STATE_FILE): 
        raise FileNotFoundError( f"{STATE_FILE} not found. Generate keys & kfrags first with your keygen script." ) 
    with open(STATE_FILE, "r") as f: 
        data = json.load(f) 
        master_public_key = PublicKey.from_bytes(b64d(data["master_public_key"])) 
        authority_public_key = PublicKey.from_bytes(b64d(data["authority_public_key"])) 
        bobs_secret_key = SecretKey.from_bytes(b64d(data["bobs_secret_key"])) 
        threshold = data.get("threshold", 4) 
        return master_public_key, authority_public_key, bobs_secret_key, threshold 
    
def main(): 
    ( master_public_key, authority_public_key, bobs_secret_key, threshold, ) = load_state() 
    bobs_public_key = bobs_secret_key.public_key() 

    plaintext = b"Proxy Re-Encryption is cool!" 
    capsule, ciphertext = encrypt(master_public_key, plaintext) 
    print("Original plaintext:", plaintext) 

    capsule_b64 = b64e(bytes(capsule)) 
    ciphertext_b64 = b64e(ciphertext) 

    NODE_PORTS = [5000, 5001, 5002, 5003, 5004, 5005, 5006] 
    NODE_URL_TEMPLATE = "http://127.0.0.1:{port}/reencrypt" 
    verified_cfrags: list[VerifiedCapsuleFrag] = [] 
    for port in NODE_PORTS: 
        url = NODE_URL_TEMPLATE.format(port=port) 
        try: 
            resp = requests.post( url, json={ "cipherText": ciphertext_b64, "capsule": capsule_b64, }, timeout=5, ) 
            resp.raise_for_status() 
        except Exception as e: 
            print(f" ❌ HTTP error from node {url}: {e}") 
            continue 
        data = resp.json() 
        cfrag_b64 = data.get("cFrag") 
        if not cfrag_b64: 
            print(f" ❌ Node {port} did not return 'cFrag' field.") 
            continue 
        try: 
            cfrag_bytes = b64d(cfrag_b64) 
        except Exception as e: 
            print(f" ❌ Node {port} returned invalid base64: {e}") 
            continue 
        # Treat this as an untrusted CapsuleFrag and verify it. 
        try: 
            suspicious_cfrag = CapsuleFrag.from_bytes(cfrag_bytes) 
        except Exception as e: 
            print(f" ❌ Node {port} returned bytes that are not a CapsuleFrag: {e}") 
            continue 
        try: 
            verified_cfrag = suspicious_cfrag.verify( capsule=capsule, verifying_pk=authority_public_key, delegating_pk=master_public_key, receiving_pk=bobs_public_key, ) 
        except VerificationError as e: 
            print(f" ❌ Verification failed for node {port}: {e}") 
            continue 
        except Exception as e: 
            print(f" ❌ Unexpected error verifying cFrag from {port}: {e}") 
            continue 
        print(f" ✅ Node {port} returned a valid cFrag.") 
        verified_cfrags.append(verified_cfrag) 
    print(f"\nCollected {len(verified_cfrags)} valid cFrags (threshold = {threshold}).") 
    if len(verified_cfrags) < threshold: 
        raise RuntimeError( f"Not enough valid cFrags to decrypt. " f"Needed {threshold}, got {len(verified_cfrags)}." )  
    shuffle(verified_cfrags) 
    bob_cleartext = decrypt_reencrypted( receiving_sk=bobs_secret_key, delegating_pk=master_public_key, capsule=capsule, verified_cfrags=verified_cfrags, ciphertext=ciphertext, ) 
    print("Decrypted via remote nodes:", bob_cleartext) 
    assert bob_cleartext == plaintext, "Decryption mismatch!" 
    print("✅ Decryption successful and matches original.") 
if __name__ == "__main__": 
    main()