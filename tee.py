import base64
import os
import json
from fastapi import FastAPI
from pydantic import BaseModel
from umbral import SecretKey, PublicKey, decrypt_reencrypted, decrypt_original, Capsule, VerifiedCapsuleFrag, encrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

STATE_FILE = "./kd/umbral_state.json"
TEE_KEY_FILE = "./tee_secret_key.json"

app = FastAPI()

# Load or generate TEE's secret key
if os.path.exists(TEE_KEY_FILE):
    with open(TEE_KEY_FILE, "r") as f:
        key_data = json.load(f)
        secret_key = SecretKey.from_bytes(base64.b64decode(key_data["secret_key"]))
    print("Loaded existing TEE secret key")
else:
    secret_key = SecretKey.random()
    with open(TEE_KEY_FILE, "w") as f:
        json.dump({"secret_key": base64.b64encode(secret_key.to_secret_bytes()).decode("utf-8")}, f)
    print("Generated new TEE secret key")

print("TEE Public Key: " + base64.b64encode(secret_key.public_key().__bytes__()).decode("utf-8"))

def b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("utf-8"))

def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("utf-8")

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

def aes_decrypt(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes | None = None):
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, aad)

def decrypt_contract_state(encrypted_state_with_key: str) -> tuple[dict, bytes]:
    """
    Decrypt contract state using TEE's private key to get the symmetric key,
    then use that to decrypt the state.
    Returns: (state_dict, symmetric_key)
    """
    encrypted_bytes = b64d(encrypted_state_with_key)
    
    # Format: capsule (98 bytes) + ciphertext (variable) + AES-GCM encrypted state
    # Umbral ciphertext for 44 bytes (32 key + 12 nonce) = 84 bytes
    capsule_size = 98
    ciphertext_size = 84
    
    capsule_bytes = encrypted_bytes[:capsule_size]
    encrypted_sym_key = encrypted_bytes[capsule_size:capsule_size + ciphertext_size]
    aes_ciphertext = encrypted_bytes[capsule_size + ciphertext_size:]
    
    # Decrypt the symmetric key using TEE's private key (Umbral decryption)
    capsule = Capsule.from_bytes(capsule_bytes)
    sym_key_with_nonce = decrypt_original(secret_key, capsule, encrypted_sym_key)
    
    sym_key = sym_key_with_nonce[:32]
    nonce = sym_key_with_nonce[32:]
    
    # Decrypt the state using AES-GCM
    state_json = aes_decrypt(sym_key, nonce, aes_ciphertext)
    state = json.loads(state_json.decode("utf-8"))
    
    return state, sym_key

def encrypt_contract_state(state: dict) -> str:
    """
    Encrypt state with a new symmetric key and encrypt that key with TEE's public key.
    Returns: base64 encoded (capsule + encrypted_key + encrypted_state)
    """
    # Generate new symmetric key
    new_sym_key = os.urandom(32)
    
    # Encrypt the state with AES-GCM
    state_json = json.dumps(state).encode("utf-8")
    nonce, encrypted_state = aes_encrypt(new_sym_key, state_json)
    
    # Encrypt the symmetric key with TEE's public key (Umbral)
    tee_public_key = secret_key.public_key()
    capsule, encrypted_sym_key = encrypt(tee_public_key, new_sym_key + nonce)
    
    # Concatenate capsule + encrypted_key + encrypted_state
    result = bytes(capsule) + encrypted_sym_key + encrypted_state
    
    return b64e(result)

@app.get("/initialize_state")
def initialize_empty_state():
    """
    Initialize empty betting state and encrypt it with TEE's public key.
    Returns encrypted state to be stored in smart contract.
    """
    try:
        empty_state = {
            "a_ratio": None,
            "votes": {}
        }
        
        encrypted_state = encrypt_contract_state(empty_state)
        
        print("Initialized empty state")
        
        return {
            "success": True,
            "encrypted_state": encrypted_state
        }
    except Exception as e:
        print(f"Initialization failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }

class SubmitVoteRequest(BaseModel):
    encrypted_vote: str  # Threshold-encrypted vote data
    encrypted_sym_key: str
    capsule: str
    cfrags: list[str]
    current_state: str  # Current encrypted state from contract

@app.post("/submit")
def process_vote(data: SubmitVoteRequest):
    """
    Process a vote:
    1. Decrypt the vote using threshold encryption
    2. Decrypt the current state
    3. Apply the vote to the state
    4. Re-encrypt the state with a new key
    5. Return the new encrypted state
    """
    try:
        master_public_key = load_state()
        
        # Decrypt the vote using threshold encryption
        vote_ciphertext = b64d(data.encrypted_vote)
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
        
        decrypted_vote = aes_decrypt(sym_key, nonce, vote_ciphertext)
        vote_data = json.loads(decrypted_vote.decode("utf-8"))
        
        print("Decrypted vote:", vote_data)
        
        # Decrypt current state from contract
        try:
            current_state, _ = decrypt_contract_state(data.current_state)
            print("Current state:", current_state)
        except Exception as state_error:
            print(f"Failed to decrypt contract state: {state_error}")
            print(f"State data length: {len(b64d(data.current_state))}")
            raise ValueError(f"Failed to decrypt contract state. The state might have been encrypted with a different TEE key. Try running initialize_betting.py again.")
        
        # Apply vote to state
        wallet_address = list(vote_data.keys())[0]
        vote_info = vote_data[wallet_address]
        
        if wallet_address in current_state["votes"]:
            return {
                "success": False,
                "error": "Wallet already voted"
            }
        
        # Add vote to state
        current_state["votes"][wallet_address] = vote_info
        
        # Recalculate a_ratio
        total_votes = len(current_state["votes"])
        a_votes = sum(1 for v in current_state["votes"].values() if v["bet_on"] == "A")
        
        if total_votes > 0:
            current_state["a_ratio"] = a_votes / total_votes
        else:
            current_state["a_ratio"] = None
        
        print("Updated state:", current_state)
        
        # Encrypt the new state with a new symmetric key
        new_encrypted_state = encrypt_contract_state(current_state)
        
        return {
            "success": True,
            "new_encrypted_state": new_encrypted_state,
            "a_ratio": current_state["a_ratio"],
        }
    except Exception as e:
        print(f"Vote processing failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }

class FinishBettingRequest(BaseModel):
    current_state: str  # Current encrypted state from contract
    winning_option: str  # "A" or "B"

@app.post("/finish")
def finish_betting(data: FinishBettingRequest):
    """
    Finish the betting and calculate payouts:
    1. Decrypt the current state
    2. Determine winners and losers based on winning_option
    3. Calculate new balances for each wallet
    4. Return the payout list (unencrypted for smart contract)
    
    Payout logic:
    - Winners split the total pool proportionally to their bets
    - Losers get 0
    """
    try:
        # Validate winning option
        if data.winning_option not in ["A", "B"]:
            return {
                "success": False,
                "error": "winning_option must be 'A' or 'B'"
            }
        
        # Decrypt current state from contract
        try:
            current_state, _ = decrypt_contract_state(data.current_state)
            print("Current state:", current_state)
        except Exception as state_error:
            print(f"Failed to decrypt contract state: {state_error}")
            raise ValueError(f"Failed to decrypt contract state: {state_error}")
        
        votes = current_state.get("votes", {})
        
        if not votes:
            return {
                "success": False,
                "error": "No votes found in the state"
            }
        
        # Calculate total pool and separate winners/losers
        total_pool = 0
        winners = {}
        losers = {}
        
        for wallet, vote_info in votes.items():
            bet_amount = vote_info["bet_amount"]
            bet_on = vote_info["bet_on"]
            total_pool += bet_amount
            
            if bet_on == data.winning_option:
                winners[wallet] = bet_amount
            else:
                losers[wallet] = bet_amount
        
        print(f"Total pool: {total_pool}")
        print(f"Winners: {len(winners)}")
        print(f"Losers: {len(losers)}")
        
        # Calculate payouts
        payouts = {}
        
        if not winners:
            # No winners - everyone gets their money back (edge case)
            for wallet, bet_amount in votes.items():
                payouts[wallet] = bet_amount
        else:
            # Winners split the total pool proportionally
            total_winner_bets = sum(winners.values())
            
            for wallet, bet_amount in winners.items():
                # Winner's share = (their bet / total winner bets) * total pool
                payout = int((bet_amount / total_winner_bets) * total_pool)
                payouts[wallet] = payout
            
            # Losers get nothing
            for wallet in losers:
                payouts[wallet] = 0
        
        # Format the result as a list for easy smart contract integration
        payout_list = [
            {
                "wallet": wallet,
                "payout": amount
            }
            for wallet, amount in payouts.items()
        ]
        
        print("Calculated payouts:", payout_list)
        
        return {
            "success": True,
            "winning_option": data.winning_option,
            "total_pool": total_pool,
            "total_winners": len(winners),
            "total_losers": len(losers),
            "payouts": payout_list
        }
    except Exception as e:
        print(f"Finish betting failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }
