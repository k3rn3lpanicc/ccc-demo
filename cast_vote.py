import os
import json
import base64

import requests

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from umbral import (
    PublicKey,
    encrypt,
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

    return master_public_key


def aes_encrypt(key: bytes, plaintext: bytes, aad: bytes | None = None):
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext, aad)
    return nonce, ct


def main():
    master_public_key = load_state()

    # Get wallet address and vote details
    wallet_address = input("Enter your wallet address: ")
    bet_amount = int(input("Enter bet amount: "))
    bet_on = input("Bet on (A/B): ").upper()
    
    if bet_on not in ["A", "B"]:
        print("Invalid choice! Must be A or B")
        return

    # Create vote data
    vote_data = {
        wallet_address: {
            "bet_amount": bet_amount,
            "bet_on": bet_on
        }
    }
    
    plaintext = json.dumps(vote_data).encode("utf-8")
    sym_key = os.urandom(32)

    # AES encrypt the vote
    nonce, sym_ciphertext = aes_encrypt(sym_key, plaintext)
    print("\nVote data:", vote_data)

    # Umbral encrypt the symmetric key + nonce
    capsule, encrypted_sym_key = encrypt(master_public_key, sym_key + nonce)
    assert len(sym_key + nonce) == 44

    capsule_b64 = b64e(bytes(capsule))
    encrypted_sym_key_b64 = b64e(encrypted_sym_key)
    vote_ciphertext_b64 = b64e(sym_ciphertext)

    # Load current state from file (in production, this would come from the contract)
    try:
        with open("contract_state.txt", "r") as f:
            current_state = f.read().strip()
    except FileNotFoundError:
        print("\n❌ contract_state.txt not found. Run initialize_betting.py first!")
        return

    # Call node's /submit_vote endpoint
    NODE_URL = "http://127.0.0.1:5000/submit_vote"
    
    print("\nSubmitting vote to node...")
    print("Node will collect cfrags and forward to TEE...")
    
    try:
        resp = requests.post(
            NODE_URL,
            json={
                "encrypted_vote": vote_ciphertext_b64,
                "encrypted_sym_key": encrypted_sym_key_b64,
                "capsule": capsule_b64,
                "current_state": current_state,
            },
            timeout=15,
        )
        resp.raise_for_status()
        
        result = resp.json()
        if result.get("success"):
            print("\n✅ Vote processed successfully!")
            print(f"Vote info: {result.get('vote_processed')}")
            print("\nNew encrypted state:")
            print(result.get('new_encrypted_state'))
            
            # Update the state file
            with open("contract_state.txt", "w") as f:
                f.write(result.get('new_encrypted_state'))
            print("\n(Updated contract_state.txt)")
        else:
            print(f"\n❌ Vote processing failed: {result.get('error')}")
    except Exception as e:
        print(f"\n❌ Failed to submit vote: {e}")


if __name__ == "__main__":
    main()
