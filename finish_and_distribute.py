import json
import requests
import os
from web3 import Web3
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

RPC_URL = os.getenv('RPC_URL', 'https://data-seed-prebsc-1-s1.binance.org:8545')
CONTRACT_ADDRESS_FILE = "contract-address.json"
CONTRACT_ABI_FILE = "contract-abi.json"
TEE_FINISH_URL = "http://127.0.0.1:8000/finish"


def main():
    print("\n" + "="*60)
    print("FINISH BETTING AND DISTRIBUTE FUNDS (BSC TESTNET)")
    print("="*60)

    # Get private key
    private_key = os.getenv('PRIVATE_KEY')
    if not private_key:
        print("\n⚠️  No private key found in .env file")
        print("Please either:")
        print("  1. Create a .env file with PRIVATE_KEY=your_key")
        print("  2. Or enter your private key now (admin only!)")
        private_key = input("\nEnter your private key (without 0x): ").strip()
        if not private_key:
            print("✗ No private key provided. Exiting.")
            return

    # Add 0x prefix if not present
    if not private_key.startswith('0x'):
        private_key = '0x' + private_key

    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print(f"X Cannot connect to network: {RPC_URL}")
        return

    print(f"✓ Connected to network")
    print(f"   Chain ID: {w3.eth.chain_id}")

    # Get account from private key
    try:
        account = w3.eth.account.from_key(private_key)
        admin = account.address
        print(f"✓ Admin account: {admin}")
    except Exception as e:
        print(f"✗ Invalid private key: {e}")
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
    
    # Verify admin
    contract_admin = contract.functions.admin().call()
    if admin.lower() != contract_admin.lower():
        print(f"✗ You are not the admin!")
        print(f"   Your address: {admin}")
        print(f"   Admin address: {contract_admin}")
        return
    print(f"✓ Admin verified")

    # List markets
    market_count = contract.functions.marketCount().call()
    print(f"\n📊 Available Markets ({market_count}):")
    
    for i in range(market_count):
        market = contract.functions.getMarket(i).call()
        title = market[1]
        status = market[5]
        status_text = ["Active", "Finished", "Payouts Set"][status]
        print(f"  {i}. {title} - {status_text}")
    
    market_choice = input(f"\nSelect market to finish (0-{market_count-1}): ")
    try:
        market_id = int(market_choice)
        if market_id < 0 or market_id >= market_count:
            raise ValueError()
    except:
        print("Invalid market, using market 0")
        market_id = 0

    market = contract.functions.getMarket(market_id).call()
    status = market[5]
    status_names = ["Active", "Finished", "PayoutsSet"]
    print(f"   Market status: {status_names[status]}")

    if status != 0:
        print("\n!!  Betting is not active for this market!")
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

        print(f"\n> Calling contract.finishBetting({market_id})...")
        try:
            nonce = w3.eth.get_transaction_count(admin)
            finish_tx = contract.functions.finishBetting(market_id).build_transaction({
                'from': admin,
                'gas': 1000000,
                'gasPrice': w3.eth.gas_price,
                'nonce': nonce,
            })

            signed_tx = w3.eth.account.sign_transaction(finish_tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            print(f"   Transaction sent: {tx_hash.hex()}")
            print("   Waiting for confirmation...")
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

            if receipt['status'] == 1:
                print(f"✓ Betting finished!")
                print(f"   Block: {receipt['blockNumber']}")
                print(f"   Gas used: {receipt['gasUsed']}")
            else:
                print(f"X Transaction failed")
                return
        except Exception as e:
            print(f"X Error finishing betting: {e}")
            import traceback
            traceback.print_exc()
            return

    print("\n" + "="*60)
    print("STEP 2: CALCULATE PAYOUTS")
    print("="*60)

    current_state = contract.functions.getCurrentState(market_id).call()
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
    all_amounts = [int(payout['payout']) for payout in payouts]  # Convert to int

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

            nonce = w3.eth.get_transaction_count(admin)
            payout_tx = contract.functions.setPayouts(
                market_id,
                batch_addresses,
                batch_amounts,
                is_last_batch
            ).build_transaction({
                'from': admin,
                'gas': 10000000,
                'gasPrice': w3.eth.gas_price,
                'nonce': nonce,
            })

            signed_tx = w3.eth.account.sign_transaction(payout_tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            print(f"   Transaction sent: {tx_hash.hex()}")
            print(f"   Waiting for confirmation...")
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
    print("\nWinners can now claim their payouts!")
    print("  - Through the frontend")
    print("  - Or use: python claim_payout.py")
    
    # Get token balance instead of ETH
    try:
        token_address = contract.functions.getTokenAddress(market_id).call()
        print(f"\nMarket token: {token_address}")
    except:
        pass


if __name__ == "__main__":
    main()
