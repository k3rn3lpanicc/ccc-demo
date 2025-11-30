import base64
import os
import json
from fastapi import FastAPI
from pydantic import BaseModel
from umbral import SecretKey, PublicKey, decrypt_reencrypted, decrypt_original, Capsule, VerifiedCapsuleFrag, encrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

STATE_FILE = "./kd/umbral_state.json"
TEE_KEY_FILE = "./kd/tee_signing_key.json"

app = FastAPI()

secret_key = SecretKey.random()
print("Generated new TEE secret key")

print("TEE Public Key: " +
      base64.b64encode(secret_key.public_key().__bytes__()).decode("utf-8"))

# Generate or load TEE Ethereum signing key
if os.path.exists(TEE_KEY_FILE):
    with open(TEE_KEY_FILE, 'r') as f:
        key_data = json.load(f)
        tee_account = Account.from_key(key_data['private_key'])
        print(f"Loaded TEE signing key from {TEE_KEY_FILE}")
else:
    tee_account = Account.create()
    key_data = {
        'private_key': tee_account.key.hex(),
        'address': tee_account.address
    }
    with open(TEE_KEY_FILE, 'w') as f:
        json.dump(key_data, f, indent=2)
    print(f"Generated new TEE signing key, saved to {TEE_KEY_FILE}")

print(f"TEE Signing Address: {tee_account.address}")
print(f"⚠️  IMPORTANT: Set this address as teeAddress in your smart contract!")
print()


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


def sign_state_transition(prev_state: str, new_state: str) -> str:
    """
    Sign a state transition (prevState, newState) using TEE's Ethereum key
    Returns the signature as hex string
    """
    # Create message hash of (prevState, newState)
    message_hash = Web3.solidity_keccak(
        ['string', 'string'],
        [prev_state, new_state]
    )
    
    # Create Ethereum signed message (adds "\x19Ethereum Signed Message:\n32" prefix)
    # This matches what toEthSignedMessageHash() expects in Solidity
    eth_message = encode_defunct(primitive=message_hash)
    
    # Sign the message
    signed_message = tee_account.sign_message(eth_message)
    
    # Return signature as hex string with 0x prefix
    signature = signed_message.signature.hex()
    if not signature.startswith('0x'):
        signature = '0x' + signature
    
    return signature


def decrypt_contract_state(encrypted_state_with_key: str) -> tuple[dict, bytes]:
    encrypted_bytes = b64d(encrypted_state_with_key)

    # Format: capsule (98 bytes) + ciphertext (variable) + AES-GCM encrypted state
    # Umbral ciphertext for 44 bytes (32 key + 12 nonce) = 84 bytes
    capsule_size = 98
    ciphertext_size = 84

    capsule_bytes = encrypted_bytes[:capsule_size]
    encrypted_sym_key = encrypted_bytes[capsule_size:capsule_size + ciphertext_size]
    aes_ciphertext = encrypted_bytes[capsule_size + ciphertext_size:]

    capsule = Capsule.from_bytes(capsule_bytes)
    sym_key_with_nonce = decrypt_original(
        secret_key, capsule, encrypted_sym_key)

    sym_key = sym_key_with_nonce[:32]
    nonce = sym_key_with_nonce[32:]

    state_json = aes_decrypt(sym_key, nonce, aes_ciphertext)
    state = json.loads(state_json.decode("utf-8"))

    return state, sym_key


def encrypt_contract_state(state: dict) -> str:
    new_sym_key = os.urandom(32)

    state_json = json.dumps(state).encode("utf-8")
    nonce, encrypted_state = aes_encrypt(new_sym_key, state_json)

    tee_public_key = secret_key.public_key()
    capsule, encrypted_sym_key = encrypt(tee_public_key, new_sym_key + nonce)

    result = bytes(capsule) + encrypted_sym_key + encrypted_state

    return b64e(result)


@app.get("/tee_address")
def get_tee_address():
    """Return the TEE's Ethereum signing address"""
    return {
        "success": True,
        "address": tee_account.address
    }


@app.get("/initialize_state")
def initialize_empty_state():
    try:
        empty_state = {
            "a_ratio": None,
            "a_funds_ratio": None,
            "votes": {}
        }

        encrypted_state = encrypt_contract_state(empty_state)
        
        # Sign the state transition (empty string -> new state)
        signature = sign_state_transition("", encrypted_state)

        print("Initialized empty state with signature")

        return {
            "success": True,
            "encrypted_state": encrypted_state,
            "signature": signature
        }
    except Exception as e:
        print(f"Initialization failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


class SubmitVoteRequest(BaseModel):
    encrypted_vote: str
    encrypted_sym_key: str
    capsule: str
    cfrags: list[str]
    current_state: str


@app.post("/submit")
def process_vote(data: SubmitVoteRequest):
    try:
        master_public_key = load_state()

        # Decrypt the vote using threshold encryption
        vote_ciphertext = b64d(data.encrypted_vote)
        encrypted_sym_key = b64d(data.encrypted_sym_key)
        capsule = Capsule.from_bytes(b64d(data.capsule))

        verified_cfrags = []
        for cfrag_b64 in data.cfrags:
            cfrag_bytes = b64d(cfrag_b64)
            verified_cfrag = VerifiedCapsuleFrag.from_verified_bytes(
                cfrag_bytes)
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

        try:
            current_state, _ = decrypt_contract_state(data.current_state)
        except Exception as state_error:
            print(f"Failed to decrypt contract state: {state_error}")
            print(f"State data length: {len(b64d(data.current_state))}")
            raise ValueError(
                f"Failed to decrypt contract state. The state might have been encrypted with a different TEE key. Try running initialize_betting.py again.")

        wallet_address = list(vote_data.keys())[0]
        vote_info = vote_data[wallet_address]

        if wallet_address in current_state["votes"]:
            return {
                "success": False,
                "error": "Wallet already voted"
            }

        current_state["votes"][wallet_address] = vote_info

        total_votes = len(current_state["votes"])
        a_votes = sum(
            1 for v in current_state["votes"].values() if v["bet_on"] == "A")

        total_funds = sum(v["bet_amount"]
                          for v in current_state["votes"].values())
        a_funds = sum(v["bet_amount"]
                      for v in current_state["votes"].values() if v["bet_on"] == "A")

        if total_votes > 0:
            current_state["a_ratio"] = a_votes / total_votes
        else:
            current_state["a_ratio"] = None

        if total_funds > 0:
            current_state["a_funds_ratio"] = a_funds / total_funds
        else:
            current_state["a_funds_ratio"] = None

        print("Updated state:", current_state)

        new_encrypted_state = encrypt_contract_state(current_state)
        
        # Sign the state transition (prev_state -> new_state)
        signature = sign_state_transition(data.current_state, new_encrypted_state)

        # Only reveal a_ratio if total votes is divisible by 5 (privacy protection)
        response = {
            "success": True,
            "new_encrypted_state": new_encrypted_state,
            "signature": signature,
            "total_votes": total_votes
        }

        if total_votes % 5 == 0:
            response["a_ratio"] = current_state["a_ratio"]
            response["a_funds_ratio"] = current_state["a_funds_ratio"]
            print(
                f"> Revealing a_ratio and a_funds_ratio (total votes: {total_votes})")
        else:
            print(f"> Hiding ratios for privacy (total votes: {total_votes})")

        return response
    except Exception as e:
        print(f"Vote processing failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


class FinishBettingRequest(BaseModel):
    current_state: str
    winning_option: str


@app.post("/finish")
def finish_betting(data: FinishBettingRequest):
    try:
        if data.winning_option not in ["A", "B"]:
            return {
                "success": False,
                "error": "winning_option must be 'A' or 'B'"
            }

        try:
            current_state, _ = decrypt_contract_state(data.current_state)
            print("Current state:", current_state)
        except Exception as state_error:
            print(f"Failed to decrypt contract state: {state_error}")
            raise ValueError(
                f"Failed to decrypt contract state: {state_error}")

        votes = current_state.get("votes", {})

        if not votes:
            return {
                "success": False,
                "error": "No votes found in the state"
            }

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

        payouts = {}

        if not winners:
            # No winners - everyone gets their money back (edge case)
            for wallet, bet_amount in votes.items():
                payouts[wallet] = bet_amount
        else:
            total_winner_bets = sum(winners.values())
            for wallet, bet_amount in winners.items():
                payout = int((bet_amount / total_winner_bets) * total_pool)
                payouts[wallet] = payout

            for wallet in losers:
                payouts[wallet] = 0

        payout_list = [
            {
                "wallet": wallet,
                "payout": amount
            }
            for wallet, amount in payouts.items()
        ]

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
