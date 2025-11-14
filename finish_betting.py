import requests

TEE_URL = "http://127.0.0.1:8000/finish"

def main():
    # Load current state from file (in production, this would come from the contract)
    try:
        with open("contract_state.txt", "r") as f:
            current_state = f.read().strip()
    except FileNotFoundError:
        print("\n❌ contract_state.txt not found. Initialize betting first!")
        return
    
    # Get winning option
    print("Finish betting and calculate payouts")
    print("=" * 50)
    winning_option = input("Enter winning option (A/B): ").upper()
    
    if winning_option not in ["A", "B"]:
        print("❌ Invalid option! Must be A or B")
        return
    
    print(f"\nFinishing betting with winner: {winning_option}")
    print("Calling TEE to calculate payouts...")
    
    try:
        resp = requests.post(
            TEE_URL,
            json={
                "current_state": current_state,
                "winning_option": winning_option,
            },
            timeout=10,
        )
        resp.raise_for_status()
        
        result = resp.json()
        
        if result.get("success"):
            print("\n✅ Betting finished successfully!")
            print("=" * 50)
            print(f"Winning option: {result['winning_option']}")
            print(f"Total pool: {result['total_pool']}")
            print(f"Total winners: {result['total_winners']}")
            print(f"Total losers: {result['total_losers']}")
            print("\nPayouts:")
            print("-" * 50)
            
            for payout_info in result['payouts']:
                wallet = payout_info['wallet']
                payout = payout_info['payout']
                # Truncate wallet for display
                short_wallet = wallet[:10] + "..." + wallet[-6:] if len(wallet) > 20 else wallet
                print(f"{short_wallet}: {payout}")
            
            print("-" * 50)
            
            # Save payouts to file
            import json
            with open("payouts.json", "w") as f:
                json.dump(result['payouts'], f, indent=2)
            print("\n(Payouts saved to payouts.json)")
            
        else:
            print(f"\n❌ Finish betting failed: {result.get('error')}")
    except Exception as e:
        print(f"\n❌ Failed to finish betting: {e}")


if __name__ == "__main__":
    main()
