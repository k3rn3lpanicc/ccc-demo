# Private Market Prediction System

A privacy-preserving betting system that uses threshold encryption and mock Trusted Execution Environment (TEE) to enable confidential voting and transparent settlement on Ethereum.

## 🎯 What is This?

This is a proof-of-concept betting platform where:

- **Users vote privately** on options A or B with ETH stakes
- **Individual votes remain encrypted** throughout the voting period
- **Vote distribution is revealed periodically** (every 5 votes) to prevent identification
- **TEE processes all votes** in a confidential manner
- **Smart contract holds funds** and enforces settlement rules
- **Winners are paid proportionally** to their stakes

## 🔐 Cryptographic Scheme

### Architecture Overview

```
User Vote → Smart Contract → Event Listener → Nodes (Threshold Re-encryption)
                ↓                                      ↓
         Encrypted State                    TEE (Decrypt & Process)
                ↓                                      ↓
         Blockchain Storage ←─────── New Encrypted State
```

### Key Components

1. **Umbral Threshold Encryption**
   - Based on proxy re-encryption
   - 7 nodes, 4-of-7 threshold (Byzantine fault tolerant)
   - Prevents single point of compromise

2. **TEE (Mock)**
   - **Note**: Due to lack of access to hardware TEE (Intel SGX, AMD SEV), this is implemented as a Python FastAPI service
   - In production, this would run in a hardware-isolated enclave
   - Holds the only private key that can decrypt votes
   - Processes votes and updates encrypted state

3. **Forward Secrecy**
   - Each state update uses a new symmetric key
   - Old keys are discarded immediately
   - Past states cannot be decrypted even if TEE is compromised later

4. **Smart Contract**
   - Holds encrypted state on-chain
   - Manages ETH deposits and payouts
   - Enforces admin controls for finishing and settlement

### Encryption Flow

#### Vote Submission

```
1. User creates vote: {address, bet_amount, bet_on: "A"/"B"}
2. Generate random symmetric key (AES-256)
3. Encrypt vote with AES-GCM
4. Encrypt symmetric key with master public key (Umbral)
5. Submit to smart contract with ETH stake
```

#### Vote Processing

```
1. Contract emits VoteSubmitted event
2. Listener detects event
3. Listener forwards vote to ONE node (e.g., node at port 5000)
4. That node collects cfrags from all other nodes (calls all 7 nodes)
5. Nodes re-encrypt using their kfrags (key fragments)
6. The coordinating node forwards vote + collected cfrags to TEE
7. TEE performs threshold decryption (needs 4+ cfrags)
8. TEE decrypts symmetric key
9. TEE decrypts vote with symmetric key
10. TEE updates state (adds vote, recalculates a_ratio)
11. TEE generates NEW symmetric key
12. TEE encrypts new state with new key
13. TEE encrypts new key with its own public key
14. TEE returns new encrypted state to node
15. Node returns result to listener
16. Listener updates contract with new encrypted state
```

#### Privacy Protection

- **A-ratio** (percentage voting for A) is only revealed when `total_votes % 5 == 0`
- This prevents identifying individual votes from ratio changes
- Provides batch transparency while maintaining voter privacy

#### Settlement

```
1. Admin calls finishBetting() → no more votes accepted
2. Admin calls TEE /finish endpoint with winning option
3. TEE decrypts final state
4. TEE calculates proportional payouts:
   winner_payout = (winner_stake / total_winner_stakes) × total_pool
5. Admin calls setPayouts() with calculated amounts
6. Winners call claimPayout() to withdraw their ETH
```

## 📋 Prerequisites

### Software Requirements

- **Python 3.12+** with pip
- **Node.js 16+** with npm
- **Git**

### Python Dependencies

```bash
pip install fastapi uvicorn web3 cryptography umbral-pre requests
```

### Node.js Dependencies

```bash
npm install
```

## 🚀 Setup and Usage

### Step 1: Start the TEE

```bash
python -m uvicorn tee:app
```

**Expected Output:**

```
Generated new TEE secret key
TEE Public Key: AzXtAf1xt7gAv8IMcXHWjkUYt0M8SfNrqD7ykWu5HWpg
INFO:     Uvicorn running on http://127.0.0.1:8000
```

**⚠️ IMPORTANT**: Copy the TEE Public Key for the next step.

**About the TEE:**

- This is a **mock TEE** implemented as a simple FastAPI service
- In production, this would run in a hardware-isolated Trusted Execution Environment (Intel SGX, AMD SEV, ARM TrustZone)
- The TEE generates a random secret key on startup
- This key is used to decrypt the final encrypted state containing votes

### Step 2: Generate Master Keys and Key Fragments

```bash
cd kd
python kd.py
```

**Prompts:**

```
Enter TEE public key (Bob's public key): <paste the key from Step 1>
```

**What this does:**

- Generates a **master key pair** for encrypting votes
- Creates an **authority key pair** for generating kfrags
- Splits the decryption capability into **7 kfrags** (key fragments)
- Sets **threshold = 4** (need 4 out of 7 nodes)
- Saves everything to `kd/umbral_state.json`

**Output:**

```json
{
  "master_public_key": "...",
  "authority_public_key": "...",
  "bobs_public_key": "...",  // TEE public key
  "kfrags": [...],  // 7 key fragments
  "threshold": 4,
  "shares": 7
}
```

### Step 3: Start the Threshold Nodes

```bash
cd ../nodes
python run_nodes.py
```

**What this does:**

- Starts 7 Flask servers on ports 5000-5006
- Each node receives one kfrag (key fragment)
- **Randomly marks 2 nodes as corrupt/malicious**
- Nodes provide re-encryption services

**Expected Output:**

```
Starting 7 Umbral nodes...
Node 0 running on http://127.0.0.1:5000 [Honest]
Node 1 running on http://127.0.0.1:5001 [Honest]
Node 2 running on http://127.0.0.1:5002 [CORRUPT]
Node 3 running on http://127.0.0.1:5003 [Honest]
Node 4 running on http://127.0.0.1:5004 [Honest]
Node 5 running on http://127.0.0.1:5005 [Honest]
Node 6 running on http://127.0.0.1:5006 [CORRUPT]

Threshold system active: Need 4+ cfrags to decrypt
Corrupt nodes may refuse to cooperate, but system remains secure!
```

**Byzantine Fault Tolerance:**

- System works even if 3 nodes are down/corrupt
- Only need 4 honest nodes out of 7

### Step 4: Start Local Ethereum Network

```bash
cd ..
npm run node
```

**What this does:**

- Starts Hardhat local Ethereum network
- Provides 20 test accounts with 10,000 ETH each
- Network runs on `http://127.0.0.1:8545`

**Keep this terminal running.**

### Step 5: Deploy Smart Contract

**New terminal:**

```bash
npx hardhat run scripts/deploy-with-tee.js --network localhost
```

**What this does:**

1. Calls TEE's `/initialize_state` endpoint
2. Gets empty encrypted state
3. Deploys `PrivateBetting.sol` contract
4. Initializes contract with encrypted state
5. Saves contract address to `contract-address.json`

**Expected Output:**

```
Deploying PrivateBetting contract with TEE initialization...

📡 Requesting initial state from TEE...
✅ Received encrypted state from TEE
   State length: 228 chars

📝 Deploying contract...
✅ PrivateBetting deployed to: 0x5FbDB2315678afecb367f032d93F642f64180aa3
   Admin address: 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266

✅ Contract address saved to contract-address.json
```

### Step 6: Start Event Listener

**New terminal:**

```bash
python contract_listener.py
```

**What this does:**

- Connects to local Ethereum network
- Listens for `VoteSubmitted` events from the contract
- When a vote is detected:
  1. Calls one node (port 5000) with the encrypted vote
  2. Node handles everything:
     - Collects cfrags from all 7 nodes (including itself)
     - Forwards vote + cfrags to TEE
     - TEE decrypts and processes vote
     - Returns new encrypted state
  3. Listener receives result and updates contract state
- Displays a_ratio when `total_votes % 5 == 0` (if revealed by TEE)

**Expected Output:**

```
============================================================
SMART CONTRACT EVENT LISTENER
============================================================
✅ Connected to Ethereum node
   Chain ID: 1337
   Latest block: 5
✅ Contract loaded: 0x5FbDB2315678afecb367f032d93F642f64180aa3
   Admin: 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
   Current state length: 228 chars

👂 Listening for VoteSubmitted events...
   Press Ctrl+C to stop

Process past events from block 0? (y/n): n
   Starting from current block: 5
```

**Keep this terminal running.**

### Step 7: Submit Votes

**New terminal:**

```bash
python submit_vote_to_contract.py
```

**Interactive prompts:**

```
Available accounts:
  1. 0x70997970...dc79C8 (10000.00 ETH)
  2. 0x3C44CdDd...07eAeE (10000.00 ETH)
  3. 0x90F79bf6...93b906 (10000.00 ETH)
  ...

Select account (1-5): 1

Bet amount in ETH (e.g., 0.1): 0.1
Bet on (A/B): A

📝 Creating vote: 0.1 ETH on A
✅ Vote encrypted

📤 Submitting to contract with 0.1 ETH...
   Transaction sent: 0x123abc...
   Waiting for confirmation...
✅ Vote submitted successfully!
   Block: 6
   Gas used: 127463

👂 The contract listener should now detect and process this vote!
```

**What happens:**

1. Vote is encrypted with AES-GCM using random symmetric key
2. Symmetric key is encrypted with master public key (Umbral)
3. Transaction sent to contract with 0.1 ETH
4. Contract emits `VoteSubmitted` event
5. **Listener processes automatically** (check listener terminal)

**Listener output:**

```
============================================================
📥 New Vote Event Detected!
============================================================
Voter: 0x70997970C51812dc3A010C7d01b50e0d17dc79C8
Amount: 0.1 ETH
Block: 6

📤 Submitting to node for processing...
  (Node will collect cfrags from all nodes and forward to TEE)
✅ Vote processed successfully!
Vote info: {'bet_amount': 100000000000000000, 'bet_on': 'A'}
Total votes: 1
🔒 A-ratio hidden for privacy (revealed every 5 votes)

📝 Updating contract state...
✅ State updated in contract (tx: 0x456def...)
============================================================
```

**Privacy Feature:**

- Votes 1-4: A-ratio hidden
- Vote 5: A-ratio revealed (e.g., 60.00%)
- Votes 6-9: Hidden again
- Vote 10: Revealed (e.g., 55.00%)

**Submit multiple votes:**

```bash
# Run multiple times with different accounts
python submit_vote_to_contract.py  # Account 2, 0.2 ETH, B
python submit_vote_to_contract.py  # Account 3, 0.15 ETH, A
python submit_vote_to_contract.py  # Account 4, 0.3 ETH, B
python submit_vote_to_contract.py  # Account 5, 0.05 ETH, A
```

**After 5th vote:**

```
📊 A-ratio revealed: 60.00%
```

### Step 8: Finish Betting and Calculate Payouts

**When voting is complete:**

```bash
python finish_and_distribute.py
```

**Interactive flow:**

```
============================================================
FINISH BETTING AND DISTRIBUTE FUNDS
============================================================
✅ Connected to Ethereum node
✅ Contract loaded: 0x5FbDB2315678afecb367f032d93F642f64180aa3
   Admin: 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
   Current status: Active

============================================================
STEP 1: FINISH BETTING
============================================================
Finish betting and close submissions? (y/n): y

📝 Calling contract.finishBetting()...
   Transaction sent: 0x789ghi...
✅ Betting finished!
   Block: 11

============================================================
STEP 2: CALCULATE PAYOUTS
============================================================
   Current state length: 450 chars

Enter winning option (A/B): A

📡 Calling TEE to calculate payouts for winner: A
✅ Payouts calculated!
   Total pool: 750000000000000000
   Winners: 3
   Losers: 2

📊 Payout breakdown:
------------------------------------------------------------
   0x70997970...dc79C8: 166666666666666666
   0x3C44CdDd...07eAeE: 333333333333333333
   0x90F79bf6...93b906: 250000000000000000
   0xOther11...111111: 0
   0xOther22...222222: 0
------------------------------------------------------------

============================================================
STEP 3: SET PAYOUTS IN CONTRACT
============================================================

Set payouts in contract? (y/n): y

📝 Setting payouts for 5 wallets...
   Transaction sent: 0xabcdef...
✅ Payouts set in contract!
   Block: 12
   Gas used: 145823

============================================================
✅ PROCESS COMPLETE!
============================================================

Winners can now claim their payouts by calling:
  contract.claimPayout()

Or use the claim script:
  python claim_payout.py

Contract balance: 0.75 ETH
```

**Payout Calculation:**

- Winners split the total pool proportionally to their stakes
- Formula: `payout = (your_stake / total_winner_stakes) × total_pool`
- Losers get 0

**Example:**

```
Total pool: 0.75 ETH
Winners (voted A):
  - Account 1: 0.1 ETH stake
  - Account 3: 0.2 ETH stake
  - Account 5: 0.15 ETH stake
  Total winner stakes: 0.45 ETH

Payouts:
  - Account 1: (0.1/0.45) × 0.75 = 0.1666 ETH
  - Account 3: (0.2/0.45) × 0.75 = 0.3333 ETH
  - Account 5: (0.15/0.45) × 0.75 = 0.25 ETH
```

### Step 9: Claim Winnings

```bash
python claim_payout.py
```

**Interactive flow:**

```
============================================================
CLAIM PAYOUT FROM CONTRACT
============================================================
✅ Connected to Ethereum node
✅ Contract loaded: 0x5FbDB2315678afecb367f032d93F642f64180aa3

Accounts with payouts:
------------------------------------------------------------
  1. 0x70997970...dc79C8
      Payout: 0.1666 ETH - 💰 Available
  2. 0x3C44CdDd...07eAeE
      Payout: 0.3333 ETH - 💰 Available
  3. 0x90F79bf6...93b906
      Payout: 0.25 ETH - 💰 Available
------------------------------------------------------------

Select account to claim (1-3): 1

📊 Account balance before: 9999.8999 ETH
   Payout amount: 0.1666 ETH

Claim payout? (y/n): y

📝 Claiming payout...
   Transaction sent: 0xfedcba...
✅ Payout claimed successfully!
   Block: 13
   Gas used: 57135

📊 Account balance after: 10000.0665 ETH
   Net change: +0.1665 ETH (payout minus gas)
```

**Run again for other winners:**

```bash
python claim_payout.py  # Claim for account 2
python claim_payout.py  # Claim for account 3
```

## 📁 Project Structure

```
private-market-prediction/
├── tee.py                          # Mock TEE service (FastAPI)
├── kd/
│   ├── kd.py                       # Key distribution setup
│   └── umbral_state.json          # Generated master keys & kfrags
├── nodes/
│   ├── node.py                     # Individual node implementation
│   └── run_nodes.py               # Starts 7 threshold nodes
├── contracts/
│   └── PrivateBetting.sol         # Solidity smart contract
├── scripts/
│   ├── deploy-with-tee.js         # Deploy with TEE initialization
│   ├── export-abi.js              # Export contract ABI
│   └── test-contract.js           # Contract testing script
├── contract_listener.py            # Event listener & processor
├── submit_vote_to_contract.py     # User vote submission
├── finish_and_distribute.py       # Admin settlement
├── claim_payout.py                # Winner claim interface
├── hardhat.config.js              # Hardhat configuration
├── package.json                    # Node.js dependencies
└── README.md                       # This file
```

## 🔒 Security Considerations

### Current Implementation (Development)

- ✅ Threshold encryption protects against node compromise
- ✅ Forward secrecy prevents historical decryption
- ✅ Byzantine fault tolerance (handles 3 corrupt nodes)
- ✅ Smart contract enforces rules and holds funds
- ⚠️  TEE is mocked (no hardware isolation)
- ⚠️  No signature verification on TEE responses
- ⚠️  Anyone can call `updateState()` (should be oracle-only)
- ⚠️  Local development network (no real stakes)

### Production Requirements

1. **Hardware TEE**
   - Intel SGX, AMD SEV, or ARM TrustZone
   - Remote attestation for verification
   - Sealed storage for keys

2. **Oracle Authorization**
   - Restrict `updateState()` to authorized oracles
   - Multi-signature for admin functions
   - Time locks for critical operations

3. **Economic Security**
   - Node operator bonds
   - Slashing for misbehavior
   - Reward mechanisms for honest operation

4. **Network Deployment**
   - Deploy on testnet (Sepolia, Goerli)
   - Then mainnet with audits
   - Distributed node operators

5. **Additional Features**
   - Time-based betting windows
   - Minimum/maximum bet limits
   - Emergency pause mechanism
   - Upgrade mechanisms

## 🧪 Testing

### Unit Tests

```bash
# Test smart contract
npx hardhat test

# Test contract with mock data
npx hardhat run scripts/test-contract.js --network localhost
```

### Integration Test

The complete flow from setup to claim is an integration test itself. Follow the usage steps above.

### What to Expect

- ✅ Votes submitted successfully
- ✅ Listener processes votes automatically
- ✅ A-ratio revealed every 5 votes
- ✅ Corrupt nodes don't break the system
- ✅ Winners can claim their proportional share
- ✅ Losers get 0
- ✅ Contract balance depletes as winners claim

## 🎓 Educational Purpose

This project demonstrates:

- **Threshold Cryptography**: Splitting trust among multiple parties
- **Proxy Re-encryption**: Umbral's approach to re-encryption
- **TEE Concepts**: Even if mocked, shows the role of trusted computing
- **Privacy Engineering**: Techniques for hiding individual actions
- **Smart Contract Integration**: Bridging off-chain computation with on-chain settlement
- **Event-Driven Architecture**: Reactive systems with blockchain events

## ⚠️ Disclaimer

**This is a proof-of-concept for educational purposes.**

- Do NOT use in production without proper security audits
- The TEE is mocked (no real hardware isolation)
- Local development only (not real money)
- No warranties or guarantees provided

## 📚 Technical References

### Cryptography

- **Umbral**: [Proxy re-encryption library](https://github.com/nucypher/nucypher)
- **AES-GCM**: Authenticated encryption with associated data
- **Threshold Cryptography**: [Shamir's Secret Sharing](https://en.wikipedia.org/wiki/Shamir%27s_Secret_Sharing)

### Trusted Execution

- **Intel SGX**: [Software Guard Extensions](https://www.intel.com/content/www/us/en/developer/tools/software-guard-extensions/overview.html)
- **AMD SEV**: [Secure Encrypted Virtualization](https://www.amd.com/en/developer/sev.html)
- **ARM TrustZone**: [ARM Trusted Execution](https://www.arm.com/technologies/trustzone-for-cortex-a)

### Smart Contracts

- **Solidity**: [Ethereum smart contract language](https://docs.soliditylang.org/)
- **Hardhat**: [Ethereum development environment](https://hardhat.org/)
- **Web3.py**: [Python Ethereum library](https://web3py.readthedocs.io/)

## 🤝 Contributing

This is an educational project. If you find issues or have improvements:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 👤 Author

Created as a demonstration of privacy-preserving smart contract systems.

---

**Remember**: This is a mock implementation. In production, replace the TEE with actual hardware-isolated trusted execution and implement all security measures.
