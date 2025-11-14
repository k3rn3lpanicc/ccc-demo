import requests

TEE_URL = "http://127.0.0.1:8000/initialize_state"

def main():
    print("Initializing empty betting state...")
    
    try:
        resp = requests.get(TEE_URL, timeout=10)
        resp.raise_for_status()
        
        result = resp.json()
        
        if result.get("success"):
            print("\n✅ State initialized successfully!")
            print("\nEncrypted state to store in contract:")
            print(result.get("encrypted_state"))
            
            # Save to file for testing
            with open("contract_state.txt", "w") as f:
                f.write(result.get("encrypted_state"))
            print("\n(Saved to contract_state.txt for testing)")
        else:
            print(f"\n❌ Initialization failed: {result.get('error')}")
    except Exception as e:
        print(f"\n❌ Failed to initialize: {e}")


if __name__ == "__main__":
    main()
