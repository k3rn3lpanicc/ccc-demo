import os
import json
import base64
from web3 import Web3
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from umbral import PublicKey, encrypt

RPC_URL = "http://127.0.0.1:8545"
CONTRACT_ADDRESS_FILE = "contract-address.json"
CONTRACT_ABI_FILE = "contract-abi.json"
TOKEN_ABI_FILE = "token-abi.json"
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

    # List available markets
    market_count = contract.functions.marketCount().call()
    print(f"\n📊 Available Markets ({market_count}):")
    
    for i in range(market_count):
        market = contract.functions.getMarket(i).call()
        title = market[1]
        status = market[4]
        status_text = ["Active", "Finished", "Payouts Set"][status]
        print(f"  {i}. {title} - {status_text}")
    
    market_choice = input(f"\nSelect market (0-{market_count-1}): ")
    try:
        market_id = int(market_choice)
        if market_id < 0 or market_id >= market_count:
            raise ValueError()
    except:
        print("Invalid market, using market 0")
        market_id = 0

    accounts = w3.eth.accounts
    if len(accounts) < 2:
        print("X Not enough accounts")
        return

    print("\nAvailable accounts:")
    for i, acc in enumerate(accounts[1:9], 1):
        token_balance = token.functions.balanceOf(acc).call()
        print(f"  {i}. {acc} ({w3.from_wei(token_balance, 'ether')} USDC)")

    choice = input("\nSelect account (1-8): ")
    try:
        voter_index = int(choice)
        voter = accounts[voter_index]
    except:
        print("Invalid choice, using account 1")
        voter = accounts[1]

    print(f"\n   Selected voter: {voter}")
    token_balance = token.functions.balanceOf(voter).call()
    print(f"   Balance: {w3.from_wei(token_balance, 'ether')} USDC")
    wallet_address = voter
    bet_usdc = input("\nBet amount in USDC (e.g., 100): ")
    try:
        bet_amount = w3.to_wei(float(bet_usdc), 'ether')
    except:
        print("Invalid amount, using 100 USDC")
        bet_amount = w3.to_wei(100, 'ether')

    bet_on = input("Bet on (A/B): ").upper()

    if bet_on not in ["A", "B"]:
        print("X Invalid choice")
        return

    vote_data = {
        wallet_address: {
            "bet_amount": bet_amount,
            "bet_on": bet_on
        }
    }

    print(
        f"\n> Creating vote for Market #{market_id}: {w3.from_wei(bet_amount, 'ether')} USDC on {bet_on}")
    master_public_key = load_master_key()
    plaintext = json.dumps(vote_data).encode("utf-8")
    sym_key = os.urandom(32)
    nonce, sym_ciphertext = aes_encrypt(sym_key, plaintext)
    capsule, encrypted_sym_key = encrypt(master_public_key, sym_key + nonce)
    vote_ciphertext_b64 = b64e(sym_ciphertext)
    encrypted_sym_key_b64 = b64e(encrypted_sym_key)
    capsule_b64 = b64e(bytes(capsule))
    print("✓ Vote encrypted")

    print(f"\n> Approving token transfer...")
    approve_tx = token.functions.approve(contract_address, bet_amount).transact({
        'from': voter,
        'gas': 100000
    })
    w3.eth.wait_for_transaction_receipt(approve_tx)
    print("✓ Token approved")

    print(
        f"\n> Submitting to contract with {w3.from_wei(bet_amount, 'ether')} USDC...")

    try:
        tx_hash = contract.functions.vote(
            market_id,
            vote_ciphertext_b64,
            encrypted_sym_key_b64,
            capsule_b64,
            bet_amount
        ).transact({
            'from': voter,
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
