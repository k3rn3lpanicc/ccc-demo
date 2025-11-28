"""
Claim payout from the smart contract
"""
import json
from web3 import Web3

# Configuration
RPC_URL = "http://127.0.0.1:8545"
CONTRACT_ADDRESS_FILE = "contract-address.json"
CONTRACT_ABI_FILE = "contract-abi.json"


def main():
    print("\n" + "="*60)
    print("CLAIM PAYOUT FROM CONTRACT")
    print("="*60)

    # Connect to Ethereum
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print("X Cannot connect to Ethereum node")
        return

    print(f"✓ Connected to Ethereum node")

    # Load contract
    with open(CONTRACT_ADDRESS_FILE, 'r') as f:
        contract_address = json.load(f)['address']

    with open(CONTRACT_ABI_FILE, 'r') as f:
        contract_abi = json.load(f)

    contract = w3.eth.contract(
        address=Web3.to_checksum_address(contract_address),
        abi=contract_abi
    )

    print(f"✓ Contract loaded: {contract_address}")

    # Get accounts
    accounts = w3.eth.accounts
    if len(accounts) < 2:
        print("X Not enough accounts")
        return

    # Show accounts with payouts
    print("\nAccounts with payouts:")
    print("-"*60)

    claimable_accounts = []
    for i, acc in enumerate(accounts[1:100], 1):  # Check first 10 accounts
        try:
            payout = contract.functions.getPayoutAmount(acc).call()
            has_claimed = contract.functions.hasClaimedPayout(acc).call()

            if payout > 0:
                status = "✓ Claimed" if has_claimed else "💰 Available"
                payout_eth = w3.from_wei(payout, 'ether')
                print(f"  {i}. {acc[:10]}...{acc[-6:]}")
                print(f"      Payout: {payout_eth} ETH - {status}")

                if not has_claimed:
                    claimable_accounts.append((i, acc, payout))
        except:
            pass

    print("-"*60)

    if not claimable_accounts:
        print("\n!  No unclaimed payouts found!")
        return

    # Select account
    choice = input(
        f"\nSelect account to claim (1-{len(claimable_accounts)}): ")

    try:
        selected_idx = int(choice)
        selected = None
        for idx, acc, payout in claimable_accounts:
            if idx == selected_idx:
                selected = (acc, payout)
                break

        if not selected:
            print("Invalid selection")
            return

        claimer, payout_amount = selected

    except:
        print("Invalid choice")
        return

    # Show balance before
    balance_before = w3.eth.get_balance(claimer)
    print(
        f"\n> Account balance before: {w3.from_wei(balance_before, 'ether')} ETH")
    print(f"   Payout amount: {w3.from_wei(payout_amount, 'ether')} ETH")

    # Confirm
    confirm = input("\nClaim payout? (y/n): ")
    if confirm.lower() != 'y':
        print("Cancelled.")
        return

    # Claim payout
    print("\n> Claiming payout...")

    try:
        tx_hash = contract.functions.claimPayout().transact({
            'from': claimer,
            'gas': 500000
        })

        print(f"   Transaction sent: {tx_hash.hex()}")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt['status'] == 1:
            print(f"✓ Payout claimed successfully!")
            print(f"   Block: {receipt['blockNumber']}")
            print(f"   Gas used: {receipt['gasUsed']}")

            # Show balance after
            balance_after = w3.eth.get_balance(claimer)
            balance_change = balance_after - balance_before

            print(
                f"\n> Account balance after: {w3.from_wei(balance_after, 'ether')} ETH")

            # Handle negative balance change (due to gas)
            if balance_change < 0:
                print(
                    f"   Net change: -{w3.from_wei(abs(balance_change), 'ether')} ETH (gas cost exceeds payout)")
            else:
                print(
                    f"   Net change: +{w3.from_wei(balance_change, 'ether')} ETH (payout minus gas)")
        else:
            print(f"X Transaction failed")

    except Exception as e:
        print(f"X Error claiming payout: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
