import os
import json
import base64
from web3 import Web3
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from umbral import PublicKey, encrypt

RPC_URL = "http://127.0.0.1:8545"
CONTRACT_ADDRESS_FILE = "contract-address.json"
CONTRACT_ABI_FILE = "contract-abi.json"
STATE_FILE = "./kd/umbral_state.json"


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


def main():
    print("\n" + "="*60)
    print("SUBMIT VOTE TO SMART CONTRACT")
    print("="*60)

    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print("X Cannot connect to Ethereum node")
        return

    print(f"✓ Connected to Ethereum node")
    print(f"   Chain ID: {w3.eth.chain_id}")

    with open(CONTRACT_ADDRESS_FILE, 'r') as f:
        contract_address = json.load(f)['address']

    with open(CONTRACT_ABI_FILE, 'r') as f:
        contract_abi = json.load(f)

    contract = w3.eth.contract(
        address=Web3.to_checksum_address(contract_address),
        abi=contract_abi
    )

    print(f"✓ Contract loaded: {contract_address}")

    accounts = w3.eth.accounts
    if len(accounts) < 2:
        print("X Not enough accounts")
        return

    print("\nAvailable accounts:")
    for i, acc in enumerate(accounts[1:9], 1):
        balance = w3.from_wei(w3.eth.get_balance(acc), 'ether')
        print(f"  {i}. {acc} ({balance:.2f} ETH)")

    choice = input("\nSelect account (1-8): ")
    try:
        voter_index = int(choice)
        voter = accounts[voter_index]
    except:
        print("Invalid choice, using account 1")
        voter = accounts[1]

    print(f"\n   Selected voter: {voter}")
    balance = w3.eth.get_balance(voter)
    print(f"   Balance: {w3.from_wei(balance, 'ether')} ETH")
    wallet_address = voter
    bet_eth = input("\nBet amount in ETH (e.g., 0.1): ")
    try:
        bet_amount_wei = w3.to_wei(float(bet_eth), 'ether')
    except:
        print("Invalid amount, using 0.1 ETH")
        bet_amount_wei = w3.to_wei(0.1, 'ether')

    bet_on = input("Bet on (A/B): ").upper()

    if bet_on not in ["A", "B"]:
        print("X Invalid choice")
        return

    vote_data = {
        wallet_address: {
            "bet_amount": bet_amount_wei,
            "bet_on": bet_on
        }
    }

    print(
        f"\n> Creating vote: {w3.from_wei(bet_amount_wei, 'ether')} ETH on {bet_on}")
    master_public_key = load_master_key()
    plaintext = json.dumps(vote_data).encode("utf-8")
    sym_key = os.urandom(32)
    nonce, sym_ciphertext = aes_encrypt(sym_key, plaintext)
    capsule, encrypted_sym_key = encrypt(master_public_key, sym_key + nonce)
    vote_ciphertext_b64 = b64e(sym_ciphertext)
    encrypted_sym_key_b64 = b64e(encrypted_sym_key)
    capsule_b64 = b64e(bytes(capsule))
    print("✓ Vote encrypted")
    print(
        f"\n> Submitting to contract with {w3.from_wei(bet_amount_wei, 'ether')} ETH...")

    try:
        tx_hash = contract.functions.vote(
            vote_ciphertext_b64,
            encrypted_sym_key_b64,
            capsule_b64
        ).transact({
            'from': voter,
            'value': bet_amount_wei,
            'gas': 3000000
        })

        print(f"   Transaction sent: {tx_hash.hex()}")

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt['status'] == 1:
            print(f"✓ Vote submitted successfully!")
        else:
            print(f"X Transaction failed")

    except Exception as e:
        print(f"X Error submitting vote: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
