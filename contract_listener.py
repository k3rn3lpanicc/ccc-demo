"""
Listen for smart contract events and process votes through nodes/TEE
"""
import json
import time
import requests
from web3 import Web3
from datetime import datetime

# Configuration
CONTRACT_ADDRESS_FILE = "contract-address.json"
CONTRACT_ABI_FILE = "contract-abi.json"
RPC_URL = "http://127.0.0.1:8545"
NODE_URL = "http://127.0.0.1:5000/submit_vote"
POLL_INTERVAL = 2  # seconds
HISTORY_FILE = "a_ratio_history.json"


def load_contract():
    """Load contract address and ABI"""
    with open(CONTRACT_ADDRESS_FILE, 'r') as f:
        contract_info = json.load(f)
        contract_address = contract_info['address']

    with open(CONTRACT_ABI_FILE, 'r') as f:
        contract_abi = json.load(f)

    return contract_address, contract_abi


def load_history():
    """Load a_ratio history from file"""
    try:
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_history(history):
    """Save a_ratio history to file"""
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)


def process_vote_event(event, contract, w3, history):
    """Process a VoteSubmitted event"""
    print("\n" + "="*60)
    print(f"> New Vote Event Detected!")
    print("="*60)

    voter = event['args']['voter']
    encrypted_vote = event['args']['encryptedVote']
    encrypted_sym_key = event['args']['encryptedSymKey']
    capsule = event['args']['capsule']
    amount = event['args']['amount']

    print(f"Voter: {voter}")
    print(f"Amount: {w3.from_wei(amount, 'ether')} USDC")
    print(f"Block: {event['blockNumber']}")

    # Get current state from contract
    current_state = contract.functions.getCurrentState().call()

    print("\n> Submitting to nodes for processing...")

    try:
        response = requests.post(
            NODE_URL,
            json={
                "encrypted_vote": encrypted_vote,
                "encrypted_sym_key": encrypted_sym_key,
                "capsule": capsule,
                "current_state": current_state,
            },
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()

        if result.get("success"):
            new_state = result.get("new_encrypted_state")
            print("✓ Vote processed successfully!")
            total_votes = result.get('total_votes', 0)
            print(f"Total votes: {total_votes}")

            # Display a_ratio and a_funds_ratio only if revealed (privacy protection)
            if "a_ratio" in result:
                a_ratio = result.get("a_ratio")
                a_funds_ratio = result.get("a_funds_ratio")
                if a_ratio is not None:
                    print(f"[:] A-ratio revealed: {a_ratio:.2%}")
                    if a_funds_ratio is not None:
                        print(
                            f"[:] A-funds-ratio revealed: {a_funds_ratio:.2%}")
                    # Save to history
                    history.append({
                        "timestamp": datetime.now().isoformat(),
                        "a_ratio": a_ratio,
                        "a_funds_ratio": a_funds_ratio,
                        "total_votes": total_votes
                    })
                    save_history(history)
                else:
                    print("> A-ratio: No votes yet")
            else:
                print("> Ratios hidden for privacy (revealed every 5 votes)")

            # Update contract state
            print("\n> Updating contract state...")

            # Get the account that will send the transaction
            # In production, this should be an authorized oracle account
            accounts = w3.eth.accounts
            if accounts:
                tx_hash = contract.functions.updateState(new_state).transact({
                    'from': accounts[0]
                })
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                print(
                    f"✓ State updated in contract (tx: {receipt.transactionHash.hex()[:10]}...)")
            else:
                print("!!  No accounts available to update state")

        else:
            print(f"X Vote processing failed: {result.get('error')}")

    except Exception as e:
        print(f"X Error processing vote: {e}")
        import traceback
        traceback.print_exc()

    print("="*60)


def main():
    print("\n" + "="*60)
    print("SMART CONTRACT EVENT LISTENER")
    print("="*60)

    # Connect to Ethereum node
    w3 = Web3(Web3.HTTPProvider(RPC_URL))

    if not w3.is_connected():
        print("X Failed to connect to Ethereum node at", RPC_URL)
        print("   Make sure Hardhat node is running: npx hardhat node")
        return

    print(f"✓ Connected to Ethereum node")
    print(f"   Chain ID: {w3.eth.chain_id}")
    print(f"   Latest block: {w3.eth.block_number}")

    # Load contract
    try:
        contract_address, contract_abi = load_contract()
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=contract_abi
        )
        print(f"✓ Contract loaded: {contract_address}")
        print(f"   Admin: {contract.functions.admin().call()}")
        print(
            f"   Current state length: {len(contract.functions.getCurrentState().call())} chars")
    except Exception as e:
        print(f"X Failed to load contract: {e}")
        print("   Make sure contract is deployed and ABI is exported")
        return

    # Load history
    history = load_history()
    print(f"   Loaded {len(history)} historical a_ratio entries")

    # Start listening for events
    print("\n> Listening for VoteSubmitted events...")
    print("   Press Ctrl+C to stop\n")

    # Track processed events
    processed_tx_hashes = set()

    # Check if we should process past events
    process_past = input(
        "Process past events from block 0? (y/n): ").lower() == 'y'

    if process_past:
        last_block = 0
        print("   Will process events from genesis block")
    else:
        last_block = w3.eth.block_number
        print(f"   Starting from current block: {last_block}")

    try:
        while True:
            current_block = w3.eth.block_number

            # Debug output every 10 seconds
            if int(time.time()) % 10 == 0:
                print(
                    f"   Polling... (last: {last_block}, current: {current_block})")

            if current_block > last_block:
                # Check for new events
                try:
                    # Use createFilter with from_block and to_block (web3.py v6+)
                    event_filter = contract.events.VoteSubmitted.create_filter(
                        from_block=last_block + 1,
                        to_block=current_block
                    )
                    events = event_filter.get_all_entries()

                    for event in events:
                        tx_hash = event['transactionHash'].hex()
                        if tx_hash not in processed_tx_hashes:
                            process_vote_event(event, contract, w3, history)
                            processed_tx_hashes.add(tx_hash)
                except Exception as e:
                    print(
                        f"!  Filter API not available, using block scanning: {e}")
                    # Fallback: scan blocks manually
                    try:
                        for block_num in range(last_block + 1, current_block + 1):
                            print(f"   Scanning block {block_num}...")
                            block = w3.eth.get_block(
                                block_num, full_transactions=True)
                            for tx in block['transactions']:
                                if tx['to'] and tx['to'].lower() == contract.address.lower():
                                    receipt = w3.eth.get_transaction_receipt(
                                        tx['hash'])
                                    print(
                                        f"   Found transaction to contract: {tx['hash'].hex()[:10]}...")
                                    # Process logs from the receipt
                                    for log in receipt['logs']:
                                        if log['address'].lower() == contract.address.lower():
                                            try:
                                                event = contract.events.VoteSubmitted().process_log(log)
                                                tx_hash = event['transactionHash'].hex(
                                                )
                                                if tx_hash not in processed_tx_hashes:
                                                    process_vote_event(
                                                        event, contract, w3, history)
                                                    processed_tx_hashes.add(
                                                        tx_hash)
                                            except Exception as e3:
                                                print(
                                                    f"   Could not process log: {e3}")
                    except Exception as e2:
                        print(f"X Error scanning blocks: {e2}")

                last_block = current_block

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\n\n> Stopping listener...")
        print("="*60)


if __name__ == "__main__":
    main()
