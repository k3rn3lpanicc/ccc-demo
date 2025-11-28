import json
import requests
from web3 import Web3

RPC_URL = "http://127.0.0.1:8545"
CONTRACT_ADDRESS_FILE = "contract-address.json"
CONTRACT_ABI_FILE = "contract-abi.json"
TEE_FINISH_URL = "http://127.0.0.1:8000/finish"


def main():
    print("\n" + "="*60)
    print("FINISH BETTING AND DISTRIBUTE FUNDS")
    print("="*60)

    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print("X Cannot connect to Ethereum node")
        return

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
    admin = accounts[0]
    print(f"   Admin: {admin}")

    status = contract.functions.status().call()
    status_names = ["Active", "Finished", "PayoutsSet"]
    print(f"   Current status: {status_names[status]}")

    if status != 0:
        print("\n!!  Betting is not active!")
        if status == 1:
            print("   Betting already finished, proceeding to payouts...")
        elif status == 2:
            print("   Payouts already set!")
            return

    if status == 0:
        print("\n" + "="*60)
        print("STEP 1: FINISH BETTING")
        print("="*60)

        confirm = input("Finish betting and close submissions? (y/n): ")
        if confirm.lower() != 'y':
            print("Cancelled.")
            return

        print("\n> Calling contract.finishBetting()...")
        try:
            tx_hash = contract.functions.finishBetting().transact({
                'from': admin,
                'gas': 1000000
            })

            print(f"   Transaction sent: {tx_hash.hex()}")
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

            if receipt['status'] == 1:
                print(f"✓ Betting finished!")
                print(f"   Block: {receipt['blockNumber']}")
            else:
                print(f"X Transaction failed")
                return
        except Exception as e:
            print(f"X Error finishing betting: {e}")
            return

    print("\n" + "="*60)
    print("STEP 2: CALCULATE PAYOUTS")
    print("="*60)

    current_state = contract.functions.getCurrentState().call()
    print(f"   Current state length: {len(current_state)} chars")

    winning_option = input("\nEnter winning option (A/B): ").upper()

    if winning_option not in ["A", "B"]:
        print("X Invalid option")
        return

    print(f"\n📡 Calling TEE to calculate payouts for winner: {winning_option}")

    try:
        response = requests.post(
            TEE_FINISH_URL,
            json={
                "current_state": current_state,
                "winning_option": winning_option
            },
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        if not result.get("success"):
            print(f"X TEE calculation failed: {result.get('error')}")
            return

        print(f"✓ Payouts calculated!")
        print(f"   Total pool: {result['total_pool']}")
        print(f"   Winners: {result['total_winners']}")
        print(f"   Losers: {result['total_losers']}")

        payouts = result['payouts']

        print("\n> Payout breakdown:")
        print("-"*60)
        for payout_info in payouts:
            wallet = payout_info['wallet']
            amount = payout_info['payout']
            short_wallet = wallet[:10] + "..." + \
                wallet[-6:] if len(wallet) > 20 else wallet
            print(f"   {short_wallet}: {amount}")
        print("-"*60)

    except Exception as e:
        print(f"X Error calculating payouts: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\n" + "="*60)
    print("STEP 3: SET PAYOUTS IN CONTRACT")
    print("="*60)

    confirm = input("\nSet payouts in contract? (y/n): ")
    if confirm.lower() != 'y':
        print("Cancelled.")
        return

    payouts = [p for p in payouts if p['payout'] > 0]

    all_addresses = [payout['wallet'] for payout in payouts]
    all_amounts = [payout['payout'] for payout in payouts]

    print(f"\n> Setting payouts for {len(all_addresses)} wallets...")

    BATCH_SIZE = 20
    total_batches = (len(all_addresses) + BATCH_SIZE - 1) // BATCH_SIZE

    print(
        f"   Using {total_batches} batch(es) of up to {BATCH_SIZE} addresses each")

    try:
        for i in range(0, len(all_addresses), BATCH_SIZE):
            batch_addresses = all_addresses[i:i + BATCH_SIZE]
            batch_amounts = all_amounts[i:i + BATCH_SIZE]
            is_last_batch = (i + BATCH_SIZE) >= len(all_addresses)

            batch_num = i // BATCH_SIZE + 1
            print(
                f"\n   Batch {batch_num}/{total_batches}: Setting {len(batch_addresses)} payouts...")

            tx_hash = contract.functions.setPayouts(
                batch_addresses,
                batch_amounts,
                is_last_batch
            ).transact({
                'from': admin,
                'gas': 10000000
            })

            print(f"   Transaction sent: {tx_hash.hex()}")
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

            if receipt['status'] == 1:
                print(f"   ✓ Batch {batch_num} complete!")
                print(f"   Block: {receipt['blockNumber']}")
                print(f"   Gas used: {receipt['gasUsed']}")
            else:
                print(f"   X Batch {batch_num} failed")
                return

        print(f"\n✓ All payouts set in contract!")
    except Exception as e:
        print(f"X Error setting payouts: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\n" + "="*60)
    print("✓ PROCESS COMPLETE!")
    print("="*60)
    print("\nWinners can now claim their payouts by calling:")
    print("  contract.claimPayout()")
    print("\nOr use the claim script:")
    print("  python claim_payout.py")

    balance = w3.eth.get_balance(contract.address)
    print(f"\nContract balance: {w3.from_wei(balance, 'ether')} ETH")


if __name__ == "__main__":
    main()
