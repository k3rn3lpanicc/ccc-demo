"""
Submit vote to contract using private key (for BSC Testnet or other networks)
"""
import os
import json
import base64
from web3 import Web3
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from umbral import PublicKey, encrypt
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
RPC_URL = os.getenv('RPC_URL', 'https://data-seed-prebsc-1-s1.binance.org:8545')
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
    print("SUBMIT VOTE TO SMART CONTRACT (BSC TESTNET)")
    print("="*60)

    # Get private key
    private_key = os.getenv('PRIVATE_KEY')
    if not private_key:
        print("\n⚠️  No private key found in .env file")
        print("Please either:")
        print("  1. Create a .env file with PRIVATE_KEY=your_key")
        print("  2. Or enter your private key now")
        private_key = input("\nEnter your private key (without 0x): ").strip()
        if not private_key:
            print("✗ No private key provided. Exiting.")
            return

    # Add 0x prefix if not present
    if not private_key.startswith('0x'):
        private_key = '0x' + private_key

    # Connect to network
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print(f"✗ Cannot connect to network: {RPC_URL}")
        return

    print(f"✓ Connected to network")
    print(f"   Chain ID: {w3.eth.chain_id}")

    # Get account from private key
    try:
        account = w3.eth.account.from_key(private_key)
        voter = account.address
        print(f"✓ Account: {voter}")
    except Exception as e:
        print(f"✗ Invalid private key: {e}")
        return

    # Load contracts
    with open(CONTRACT_ADDRESS_FILE, 'r') as f:
        contract_info = json.load(f)
        contract_address = contract_info['address']

    with open(CONTRACT_ABI_FILE, 'r') as f:
        contract_abi = json.load(f)

    with open(TOKEN_ABI_FILE, 'r') as f:
        token_abi = json.load(f)

    contract = w3.eth.contract(
        address=Web3.to_checksum_address(contract_address),
        abi=contract_abi
    )

    print(f"✓ Contract loaded: {contract_address}")

    # List available markets
    market_count = contract.functions.marketCount().call()
    print(f"\n📊 Available Markets ({market_count}):")
    
    for i in range(market_count):
        market = contract.functions.getMarket(i).call()
        title = market[1]
        market_token = market[3]
        status = market[5]
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

    # Get the token for the selected market
    token_address = contract.functions.getTokenAddress(market_id).call()
    token = w3.eth.contract(
        address=Web3.to_checksum_address(token_address),
        abi=token_abi
    )
    print(f"✓ Market token loaded: {token_address}")

    # Check balance
    token_balance = token.functions.balanceOf(voter).call()
    print(f"\n   Your token balance: {w3.from_wei(token_balance, 'ether')} tokens")

    # Get bet details
    bet_input = input("\nBet amount (e.g., 100): ")
    try:
        bet_amount = w3.to_wei(float(bet_input), 'ether')
    except:
        print("Invalid amount, using 100 tokens")
        bet_amount = w3.to_wei(100, 'ether')

    bet_on = input("Bet on (A/B): ").upper()

    if bet_on not in ["A", "B"]:
        print("✗ Invalid choice")
        return

    # Create and encrypt vote
    vote_data = {
        voter: {
            "bet_amount": bet_amount,
            "bet_on": bet_on
        }
    }

    print(f"\n> Creating vote for Market #{market_id}: {w3.from_wei(bet_amount, 'ether')} tokens on {bet_on}")
    master_public_key = load_master_key()
    plaintext = json.dumps(vote_data).encode("utf-8")
    sym_key = os.urandom(32)
    nonce, sym_ciphertext = aes_encrypt(sym_key, plaintext)
    capsule, encrypted_sym_key = encrypt(master_public_key, sym_key + nonce)
    vote_ciphertext_b64 = b64e(sym_ciphertext)
    encrypted_sym_key_b64 = b64e(encrypted_sym_key)
    capsule_b64 = b64e(bytes(capsule))
    print("✓ Vote encrypted")

    # Approve token
    print(f"\n> Approving token transfer...")
    try:
        nonce = w3.eth.get_transaction_count(voter)
        approve_tx = token.functions.approve(contract_address, bet_amount).build_transaction({
            'from': voter,
            'gas': 100000,
            'gasPrice': w3.eth.gas_price,
            'nonce': nonce,
        })
        
        signed_approve = w3.eth.account.sign_transaction(approve_tx, private_key)
        approve_hash = w3.eth.send_raw_transaction(signed_approve.raw_transaction)
        approve_receipt = w3.eth.wait_for_transaction_receipt(approve_hash)
        print("✓ Token approved")
    except Exception as e:
        print(f"✗ Failed to approve token: {e}")
        return

    # Submit vote
    print(f"\n> Submitting to contract with {w3.from_wei(bet_amount, 'ether')} tokens...")

    try:
        nonce = w3.eth.get_transaction_count(voter)
        vote_tx = contract.functions.vote(
            market_id,
            vote_ciphertext_b64,
            encrypted_sym_key_b64,
            capsule_b64,
            bet_amount
        ).build_transaction({
            'from': voter,
            'gas': 3000000,
            'gasPrice': w3.eth.gas_price,
            'nonce': nonce,
        })

        signed_vote = w3.eth.account.sign_transaction(vote_tx, private_key)
        vote_hash = w3.eth.send_raw_transaction(signed_vote.raw_transaction)
        
        print(f"   Transaction sent: {vote_hash.hex()}")
        print("   Waiting for confirmation...")

        receipt = w3.eth.wait_for_transaction_receipt(vote_hash)

        if receipt['status'] == 1:
            print(f"✓ Vote submitted successfully!")
            print(f"   Block: {receipt['blockNumber']}")
            print(f"   Gas used: {receipt['gasUsed']}")
        else:
            print(f"✗ Transaction failed")

    except Exception as e:
        print(f"✗ Error submitting vote: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*60)
    print("👂 The contract listener should now detect and process this vote!")
    print("="*60)


if __name__ == "__main__":
    main()
