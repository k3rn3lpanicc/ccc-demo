"""
Complete test of the betting system flow
"""
import os
import json
import base64
import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from umbral import PublicKey, encrypt

STATE_FILE = "./kd/umbral_state.json"
TEE_INIT_URL = "http://127.0.0.1:8000/initialize_state"
NODE_URL = "http://127.0.0.1:5000/submit_vote"
TEE_FINISH_URL = "http://127.0.0.1:8000/finish"


def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("utf-8")


def b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("utf-8"))


def load_master_key():
    with open(STATE_FILE, "r") as f:
        data = json.load(f)
    return PublicKey.from_bytes(b64d(data["master_public_key"]))


def aes_encrypt(key: bytes, plaintext: bytes):
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext, None)
    return nonce, ct


def cast_vote(wallet, amount, choice, current_state):
    """Encrypt and submit a vote"""
    master_public_key = load_master_key()
    
    vote_data = {wallet: {"bet_amount": amount, "bet_on": choice}}
    plaintext = json.dumps(vote_data).encode("utf-8")
    sym_key = os.urandom(32)
    
    nonce, sym_ciphertext = aes_encrypt(sym_key, plaintext)
    capsule, encrypted_sym_key = encrypt(master_public_key, sym_key + nonce)
    
    resp = requests.post(
        NODE_URL,
        json={
            "encrypted_vote": b64e(sym_ciphertext),
            "encrypted_sym_key": b64e(encrypted_sym_key),
            "capsule": b64e(bytes(capsule)),
            "current_state": current_state,
        },
        timeout=15,
    )
    resp.raise_for_status()
    result = resp.json()
    
    if not result.get("success"):
        raise Exception(f"Vote failed: {result.get('error')}")
    
    return result.get("new_encrypted_state")


def main():
    print("\n" + "="*60)
    print("TESTING COMPLETE BETTING FLOW")
    print("="*60)
    
    # Step 1: Initialize
    print("\n1. Initializing betting state...")
    resp = requests.get(TEE_INIT_URL, timeout=10)
    resp.raise_for_status()
    result = resp.json()
    
    if not result.get("success"):
        print(f"❌ Initialization failed: {result.get('error')}")
        return
    
    current_state = result.get("encrypted_state")
    print("✅ State initialized")
    
    # Step 2: Cast votes
    print("\n2. Casting votes...")
    
    votes = [
        ("0xAlice", 100, "A"),
        ("0xBob", 200, "A"),
        ("0xCharlie", 150, "B"),
        ("0xDave", 50, "B"),
        ("0xEve", 300, "A"),
    ]
    
    for wallet, amount, choice in votes:
        print(f"   - {wallet}: {amount} on {choice}")
        current_state = cast_vote(wallet, amount, choice, current_state)
    
    print("✅ All votes cast")
    
    # Save state to file
    with open("contract_state.txt", "w") as f:
        f.write(current_state)
    
    # Step 3: View state
    print("\n3. Current state summary:")
    print("   Total bets: 5")
    print("   Total pool: 800")
    print("   A votes: 3 (Alice, Bob, Eve) = 600")
    print("   B votes: 2 (Charlie, Dave) = 200")
    
    # Step 4: Finish betting
    print("\n4. Finishing betting...")
    winning_option = input("   Enter winning option (A/B): ").upper()
    
    if winning_option not in ["A", "B"]:
        print("❌ Invalid option")
        return
    
    resp = requests.post(
        TEE_FINISH_URL,
        json={
            "current_state": current_state,
            "winning_option": winning_option,
        },
        timeout=10,
    )
    resp.raise_for_status()
    result = resp.json()
    
    if not result.get("success"):
        print(f"❌ Finish failed: {result.get('error')}")
        return
    
    print(f"✅ Betting finished! Winner: {winning_option}")
    
    # Step 5: Display payouts
    print("\n5. Payouts:")
    print("="*60)
    print(f"Total pool: {result['total_pool']}")
    print(f"Winners: {result['total_winners']}")
    print(f"Losers: {result['total_losers']}")
    print("\nPayout details:")
    print("-"*60)
    
    for payout_info in result['payouts']:
        wallet = payout_info['wallet']
        payout = payout_info['payout']
        print(f"{wallet}: {payout}")
    
    print("-"*60)
    
    # Save payouts
    with open("payouts.json", "w") as f:
        json.dump(result['payouts'], f, indent=2)
    
    print("\n✅ Test completed successfully!")
    print("   Payouts saved to payouts.json")


if __name__ == "__main__":
    main()
