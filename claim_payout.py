"""
Claim payout from the smart contract
"""
import json
from web3 import Web3

# Configuration
RPC_URL = "http://127.0.0.1:8545"
CONTRACT_ADDRESS_FILE = "contract-address.json"
CONTRACT_ABI_FILE = "contract-abi.json"
TOKEN_ABI_FILE = "token-abi.json"


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

    # List markets
    market_count = contract.functions.marketCount().call()
    print(f"\n📊 Available Markets ({market_count}):")
    
    for i in range(market_count):
        market = contract.functions.getMarket(i).call()
        title = market[1]
        status = market[4]
        status_text = ["Active", "Finished", "Payouts Set"][status]
        print(f"  {i}. {title} - {status_text}")
    
    market_choice = input(f"\nSelect market to claim from (0-{market_count-1}): ")
    try:
        market_id = int(market_choice)
        if market_id < 0 or market_id >= market_count:
            raise ValueError()
    except:
        print("Invalid market, using market 0")
        market_id = 0

    # Get accounts
    accounts = w3.eth.accounts
    if len(accounts) < 2:
        print("X Not enough accounts")
        return

    # Show accounts with payouts for this market
    print(f"\nAccounts with payouts for Market #{market_id}:")
    print("-"*60)

    claimable_accounts = []
    for i, acc in enumerate(accounts[1:100], 1):
        try:
            payout = contract.functions.getPayoutAmount(market_id, acc).call()
            has_claimed = contract.functions.hasClaimedPayout(market_id, acc).call()

            if payout > 0:
                status = "✓ Claimed" if has_claimed else "💰 Available"
                payout_usdc = w3.from_wei(payout, 'ether')
                print(f"  {i}. {acc[:10]}...{acc[-6:]}")
                print(f"      Payout: {payout_usdc} USDC - {status}")

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
    balance_before = token.functions.balanceOf(claimer).call()
    print(
        f"\n> Account balance before: {w3.from_wei(balance_before, 'ether')} USDC")
    print(f"   Payout amount: {w3.from_wei(payout_amount, 'ether')} USDC")

    # Confirm
    confirm = input("\nClaim payout? (y/n): ")
    if confirm.lower() != 'y':
        print("Cancelled.")
        return

    # Claim payout
    print("\n> Claiming payout...")

    try:
        tx_hash = contract.functions.claimPayout(market_id).transact({
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
            balance_after = token.functions.balanceOf(claimer).call()
            balance_change = balance_after - balance_before

            print(
                f"\n> Account balance after: {w3.from_wei(balance_after, 'ether')} USDC")
            print(
                f"   Net change: +{w3.from_wei(balance_change, 'ether')} USDC")
        else:
            print(f"X Transaction failed")

    except Exception as e:
        print(f"X Error claiming payout: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
