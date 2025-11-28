"""
Automated voting script - submits votes from accounts 10-49 with random amounts and choices
"""
import os
import json
import base64
import random
import time
from web3 import Web3
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from umbral import PublicKey, encrypt

RPC_URL = "http://127.0.0.1:8545"
CONTRACT_ADDRESS_FILE = "contract-address.json"
CONTRACT_ABI_FILE = "contract-abi.json"
TOKEN_ABI_FILE = "token-abi.json"
STATE_FILE = "./kd/umbral_state.json"

# Configuration
START_ACCOUNT = 45
END_ACCOUNT = 65
MIN_BET = 100  # USDC
MAX_BET = 10000  # USDC
DELAY_BETWEEN_VOTES = 0.5  # seconds

# Voting behavior configuration
A_VOTE_PROBABILITY = 0.65  # 65% chance to vote for A
A_HIGH_BET_PROBABILITY = 0.3  # 30% of A voters bet high (5-10 ETH)
B_HIGH_BET_PROBABILITY = 0.7  # 70% of B voters bet high (5-10 ETH)

# This creates interesting divergence:
# - More people vote for A (65% vs 35%)
# - But B voters bet more aggressively
# - Result: A wins in vote count, but funds ratio is closer or even favors B


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


def submit_vote(w3, contract, token, voter_address, bet_amount_usdc, bet_on, master_public_key):
    """Submit a single encrypted vote"""
    bet_amount = w3.to_wei(bet_amount_usdc, 'ether')

    # Create vote data
    vote_data = {
        voter_address: {
            "bet_amount": bet_amount,
            "bet_on": bet_on
        }
    }

    # Encrypt vote
    plaintext = json.dumps(vote_data).encode("utf-8")
    sym_key = os.urandom(32)
    nonce, sym_ciphertext = aes_encrypt(sym_key, plaintext)
    capsule, encrypted_sym_key = encrypt(master_public_key, sym_key + nonce)

    vote_ciphertext_b64 = b64e(sym_ciphertext)
    encrypted_sym_key_b64 = b64e(encrypted_sym_key)
    capsule_b64 = b64e(bytes(capsule))

    # Approve token transfer
    contract_address = contract.address
    approve_tx = token.functions.approve(contract_address, bet_amount).transact({
        'from': voter_address,
        'gas': 100000
    })
    w3.eth.wait_for_transaction_receipt(approve_tx)

    # Submit to contract
    tx_hash = contract.functions.vote(
        vote_ciphertext_b64,
        encrypted_sym_key_b64,
        capsule_b64,
        bet_amount
    ).transact({
        'from': voter_address,
        'gas': 3000000
    })

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return receipt['status'] == 1, tx_hash.hex()


def main():
    print("\n" + "="*70)
    print("AUTOMATED VOTING SCRIPT")
    print("="*70)
    print(f"Accounts: {START_ACCOUNT} to {END_ACCOUNT}")
    print(f"Bet range: {MIN_BET} to {MAX_BET} USDC")
    print(f"Delay between votes: {DELAY_BETWEEN_VOTES} seconds")
    print()
    print("Voting Strategy:")
    print(f"  - {A_VOTE_PROBABILITY*100:.0f}% likely to vote for A (majority)")
    print(
        f"  - A voters: {A_HIGH_BET_PROBABILITY*100:.0f}% bet high, {(1-A_HIGH_BET_PROBABILITY)*100:.0f}% bet low")
    print(
        f"  - B voters: {B_HIGH_BET_PROBABILITY*100:.0f}% bet high, {(1-B_HIGH_BET_PROBABILITY)*100:.0f}% bet low")
    print(f"  → Expect: More A votes, but B has more funds!")
    print("="*70 + "\n")

    # Connect to Ethereum
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print("X Cannot connect to Ethereum node")
        return

    print("✓ Connected to Ethereum node")

    # Load contract
    with open(CONTRACT_ADDRESS_FILE, 'r') as f:
        contract_info = json.load(f)
        contract_address = contract_info['address']
        token_address = contract_info['tokenAddress']

    with open(CONTRACT_ABI_FILE, 'r') as f:
        contract_abi = json.load(f)

    with open(TOKEN_ABI_FILE, 'r') as f:
        token_abi = json.load(f)

    contract = w3.eth.contract(
        address=Web3.to_checksum_address(contract_address),
        abi=contract_abi
    )

    token = w3.eth.contract(
        address=Web3.to_checksum_address(token_address),
        abi=token_abi
    )

    print(f"✓ Contract loaded: {contract_address}")
    print(f"✓ Token loaded: {token_address}")

    # Load master key
    master_public_key = load_master_key()
    print("✓ Master key loaded")

    # Get accounts
    accounts = w3.eth.accounts

    if len(accounts) < END_ACCOUNT + 1:
        print(
            f"X Not enough accounts. Available: {len(accounts)}, Needed: {END_ACCOUNT + 1}")
        return

    print(f"✓ Found {len(accounts)} accounts\n")

    # Confirm before starting
    confirm = input("Start automated voting? (y/n): ")
    if confirm.lower() != 'y':
        print("Cancelled.")
        return

    print("\n" + "="*70)
    print("STARTING AUTOMATED VOTING...")
    print("="*70 + "\n")

    success_count = 0
    fail_count = 0
    total_a_votes = 0
    total_b_votes = 0
    total_a_funds = 0.0
    total_b_funds = 0.0

    # Vote with each account
    for account_index in range(START_ACCOUNT, END_ACCOUNT + 1):
        voter_address = accounts[account_index]

        # Determine vote choice with bias
        bet_on = 'A' if random.random() < A_VOTE_PROBABILITY else 'B'

        # Determine bet amount based on choice
        if bet_on == 'A':
            # A voters: mostly small to medium bets
            if random.random() < A_HIGH_BET_PROBABILITY:
                bet_amount = round(random.uniform(5000, MAX_BET), 2)  # High bet
            else:
                bet_amount = round(random.uniform(
                    MIN_BET, 3000), 2)  # Low to medium bet
        else:
            # B voters: mostly high bets
            if random.random() < B_HIGH_BET_PROBABILITY:
                bet_amount = round(random.uniform(5000, MAX_BET), 2)  # High bet
            else:
                bet_amount = round(random.uniform(
                    MIN_BET, 3000), 2)  # Low to medium bet

        # Track stats
        if bet_on == 'A':
            total_a_votes += 1
            total_a_funds += bet_amount
        else:
            total_b_votes += 1
            total_b_funds += bet_amount

        print(
            f"[{account_index}/{END_ACCOUNT}] Account {account_index}: {voter_address[:10]}...")
        print(f"           Voting: {bet_on} with {bet_amount} USDC")

        try:
            success, tx_hash = submit_vote(
                w3, contract, token, voter_address, bet_amount, bet_on, master_public_key
            )

            if success:
                print(f"           ✓ Success! Tx: {tx_hash[:20]}...")
                success_count += 1
            else:
                print(f"           X Transaction failed")
                fail_count += 1

        except Exception as e:
            print(f"           X Error: {e}")
            fail_count += 1

        # Wait before next vote (except for last one)
        if account_index < END_ACCOUNT:
            print(f"           ⏳ Waiting {DELAY_BETWEEN_VOTES} seconds...\n")
            time.sleep(DELAY_BETWEEN_VOTES)
        else:
            print()

    # Summary
    total_votes = success_count + fail_count
    total_funds = total_a_funds + total_b_funds

    print("="*70)
    print("VOTING COMPLETE!")
    print("="*70)
    print(f"✓ Successful votes: {success_count}")
    print(f"X Failed votes: {fail_count}")
    print(f"> Total votes: {total_votes}")
    print()
    print("Vote Distribution:")
    print(
        f"   Option A: {total_a_votes} votes ({total_a_votes/total_votes*100:.1f}%)")
    print(
        f"   Option B: {total_b_votes} votes ({total_b_votes/total_votes*100:.1f}%)")
    print()
    print("Funds Distribution:")
    print(
        f"   Option A: {total_a_funds:.2f} USDC ({total_a_funds/total_funds*100:.1f}%)")
    print(
        f"   Option B: {total_b_funds:.2f} USDC ({total_b_funds/total_funds*100:.1f}%)")
    print(f"   Total: {total_funds:.2f} USDC")
    print()
    print("> Wait a few seconds for the listener to process all votes...")
    print("   Then check the frontend to see the updated ratios!")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
