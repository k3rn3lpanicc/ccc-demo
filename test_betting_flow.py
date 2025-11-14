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
        # Early adopters - Team A
        ("0xAlice1234567890abcdef1234567890abcdef1234", 100, "A"),
        ("0xBob1234567890abcdef1234567890abcdef123456", 200, "A"),
        ("0xCharlie1234567890abcdef1234567890abcdef12", 150, "B"),
        ("0xDave1234567890abcdef1234567890abcdef12345", 50, "B"),
        ("0xEve1234567890abcdef1234567890abcdef123456", 300, "A"),
        
        # Whale bettors
        ("0xWhale11234567890abcdef1234567890abcdef1234", 5000, "A"),
        ("0xWhale21234567890abcdef1234567890abcdef1234", 4500, "B"),
        ("0xWhale31234567890abcdef1234567890abcdef1234", 3200, "A"),
        
        # Medium bettors - Team A
        ("0xFrank1234567890abcdef1234567890abcdef12345", 500, "A"),
        ("0xGrace1234567890abcdef1234567890abcdef12345", 750, "A"),
        ("0xHenry1234567890abcdef1234567890abcdef12345", 420, "A"),
        ("0xIsabel1234567890abcdef1234567890abcdef1234", 680, "A"),
        ("0xJack1234567890abcdef1234567890abcdef123456", 320, "A"),
        
        # Medium bettors - Team B
        ("0xKate1234567890abcdef1234567890abcdef123456", 550, "B"),
        ("0xLiam1234567890abcdef1234567890abcdef123456", 890, "B"),
        ("0xMia1234567890abcdef1234567890abcdef1234567", 470, "B"),
        ("0xNoah1234567890abcdef1234567890abcdef123456", 620, "B"),
        
        # Small bettors - Team A
        ("0xOlivia1234567890abcdef1234567890abcdef1234", 50, "A"),
        ("0xPeter1234567890abcdef1234567890abcdef12345", 75, "A"),
        ("0xQuinn1234567890abcdef1234567890abcdef12345", 100, "A"),
        ("0xRose1234567890abcdef1234567890abcdef123456", 125, "A"),
        ("0xSam1234567890abcdef1234567890abcdef1234567", 80, "A"),
        
        # Small bettors - Team B
        ("0xTina1234567890abcdef1234567890abcdef123456", 60, "B"),
        ("0xUma1234567890abcdef1234567890abcdef1234567", 90, "B"),
        ("0xVic1234567890abcdef1234567890abcdef1234567", 110, "B"),
        ("0xWendy1234567890abcdef1234567890abcdef12345", 70, "B"),
        
        # Late joiners - Team A
        ("0xXander1234567890abcdef1234567890abcdef1234", 1200, "A"),
        ("0xYara1234567890abcdef1234567890abcdef123456", 850, "A"),
        ("0xZack1234567890abcdef1234567890abcdef123456", 960, "A"),
        
        # Late joiners - Team B
        ("0xAdam1234567890abcdef1234567890abcdef123456", 1100, "B"),
        ("0xBella1234567890abcdef1234567890abcdef12345", 780, "B"),
        ("0xCody1234567890abcdef1234567890abcdef123456", 920, "B"),
        
        # Random mix
        ("0xDiana1234567890abcdef1234567890abcdef12345", 340, "A"),
        ("0xEthan1234567890abcdef1234567890abcdef12345", 560, "B"),
        ("0xFiona1234567890abcdef1234567890abcdef12345", 440, "A"),
        ("0xGeorge1234567890abcdef1234567890abcdef1234", 710, "B"),
        ("0xHannah1234567890abcdef1234567890abcdef1234", 290, "A"),
        ("0xIan1234567890abcdef1234567890abcdef1234567", 830, "B"),
        ("0xJulia1234567890abcdef1234567890abcdef12345", 370, "A"),
        ("0xKevin1234567890abcdef1234567890abcdef12345", 640, "B"),
    ]
    
    total_a = sum(amount for _, amount, choice in votes if choice == "A")
    total_b = sum(amount for _, amount, choice in votes if choice == "B")
    total_pool = total_a + total_b
    count_a = sum(1 for _, _, choice in votes if choice == "A")
    count_b = sum(1 for _, _, choice in votes if choice == "B")
    
    for i, (wallet, amount, choice) in enumerate(votes, 1):
        print(f"   [{i}/{len(votes)}] {wallet[:10]}...{wallet[-6:]}: {amount} on {choice}")
        current_state = cast_vote(wallet, amount, choice, current_state)
    
    print(f"✅ All {len(votes)} votes cast")
    
    # Save state to file
    with open("contract_state.txt", "w") as f:
        f.write(current_state)
    
    # Step 3: View state
    print("\n3. Current state summary:")
    print("="*60)
    print(f"   Total bets: {len(votes)}")
    print(f"   Total pool: {total_pool:,}")
    print(f"   A votes: {count_a} participants = {total_a:,} total")
    print(f"   B votes: {count_b} participants = {total_b:,} total")
    print(f"   A ratio: {count_a/len(votes):.1%}")
    print("="*60)
    
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
