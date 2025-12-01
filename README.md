# Private Market Prediction System

A privacy-preserving, multi-market prediction platform that uses threshold encryption and mock Trusted Execution Environment (TEE) to enable confidential voting and transparent settlement on Ethereum.

## What is This?

This is a proof-of-concept prediction market platform where:

- **Multiple markets** can exist simultaneously in one smart contract
- **Admin creates markets** with custom titles and descriptions (Polymarket-style)
- **Users browse markets** on a landing page and select which to participate in
- **Users vote privately** on options A or B with USDC tokens via a web interface
- **Individual votes remain encrypted** throughout the voting period
- **Vote distribution is revealed periodically** (every 5 votes) to prevent identification
- **Two metrics tracked**: A-ratio (vote count) and A-funds-ratio (funds amount)
- **Real-time visualization** shows both metrics on an interactive chart per market
- **TEE processes all votes** in a confidential manner
- **Smart contract holds funds** and enforces settlement rules
- **Winners are paid proportionally** to their stakes
- **Automated voting** script available for testing with multiple accounts
- **Admin authentication** required for market creation

## Cryptographic Scheme

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
   - **Signs all state transitions** with Ethereum private key
   - Generates persistent signing key on first run

3. **Forward Secrecy**
   - Each state update uses a new symmetric key
   - Old keys are discarded immediately
   - Past states cannot be decrypted even if TEE is compromised later

4. **Smart Contract**
   - Holds encrypted state on-chain
   - Manages ERC20 token (USDC) deposits and payouts
   - Enforces admin controls for finishing and settlement
   - **Verifies TEE signatures** on all state updates
   - Stores TEE address and rejects unsigned state transitions

### Encryption Flow

#### Vote Submission

```
1. User creates vote: {address, bet_amount, bet_on: "A"/"B"}
2. Generate random symmetric key (AES-256)
3. Encrypt vote with AES-GCM
4. Encrypt symmetric key with master public key (Umbral)
5. Approve USDC token transfer to contract
6. Submit to smart contract with USDC amount
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
14. TEE signs (prevState, newState) with Ethereum private key
15. TEE returns new encrypted state + signature to node
16. Node returns result to listener
17. Listener updates contract with new encrypted state + signature
18. Contract verifies TEE signature before accepting state update
```

#### Privacy Protection

- **A-ratio** (percentage voting for A) is only revealed when `total_votes % 5 == 0`
- **A-funds-ratio** (percentage of funds on A) is also revealed at the same intervals
- This prevents identifying individual votes from ratio changes
- Provides batch transparency while maintaining voter privacy
- Historical data is tracked and visualized in real-time chart

#### Settlement

```
1. Admin calls finishBetting() → no more votes accepted
2. Admin calls TEE /finish endpoint with winning option
3. TEE decrypts final state
4. TEE calculates proportional payouts:
   winner_payout = (winner_stake / total_winner_stakes) × total_pool
5. Admin calls setPayouts() with calculated amounts
6. Winners call claimPayout() to withdraw their USDC
```

## Prerequisites

### Software Requirements

- **Python 3.12+** with pip
- **Node.js 16+** with npm
- **Git**
- **MetaMask** browser extension for wallet interaction
- **BSC Testnet** tokens (BNB for gas fees)

### Python Dependencies

```bash
pip install fastapi uvicorn web3 cryptography umbral-pre requests python-dotenv
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
Generated new TEE signing key, saved to ./kd/tee_signing_key.json
TEE Signing Address: 0x25fb079F3A0f60333cdB3BC2dE7Af6d7B7EF5DA0
⚠️  IMPORTANT: Set this address as teeAddress in your smart contract!

INFO:     Uvicorn running on http://127.0.0.1:8000
```

**⚠️ IMPORTANT**: 
- Copy the **TEE Public Key** for the next step (key distribution)
- Copy the **TEE Signing Address** - the deployment script will use this automatically

**About the TEE:**

- This is a **mock TEE** implemented as a simple FastAPI service
- In production, this would run in a hardware-isolated Trusted Execution Environment (Intel SGX, AMD SEV, ARM TrustZone)
- The TEE generates two keys on startup:
  - **Umbral secret key**: Used to decrypt the final encrypted state containing votes
  - **Ethereum signing key**: Used to sign all state transitions for verification by the smart contract
- Keys are persisted to disk for consistency across restarts

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
  "tee_public_key": "...",  // TEE public key
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

### Step 4: Deploy Smart Contract to BSC Testnet

**⚠️ IMPORTANT**: This project is deployed on **BSC Testnet**, not a local Hardhat node.

**Prerequisites:**
- Admin wallet with BNB for gas fees on BSC Testnet
- Admin private key stored in `.env` file or environment variable

**Deployment:**

The contract has already been deployed to BSC Testnet. The deployment details are stored in `contract-address.json`:

```json
{
  "contract": "0x...",  // PrivateBetting contract
  "token": "0x...",     // Payment token (e.g., USDC, DAI)
  "deployer": "0x...",  // Admin address
  "teeAddress": "0x..." // TEE signing address
}
```

**Network Configuration:**
- **RPC URL**: `https://data-seed-prebsc-1-s1.binance.org:8545/`
- **Chain ID**: 97 (BSC Testnet)
- **Block Explorer**: https://testnet.bscscan.com/

**Note**: Each market can use a different ERC20 payment token (USDC, DAI, etc.). The token address is specified when creating a market.

### Step 5: Start Event Listener

**⚠️ IMPORTANT**: Configure admin private key before starting the listener!

**Create a `.env` file** in the project root:

```bash
ADMIN_PRIVATE_KEY=your_admin_private_key_here
```

**Start the listener:**

```bash
python contract_listener.py
```

**What this does:**

- Connects to **BSC Testnet** via RPC URL
- Listens for `VoteSubmitted` events from the contract
- When a vote is detected:
  1. Calls one node (port 5000) with the encrypted vote
  2. Node handles everything:
     - Collects cfrags from all 7 nodes (including itself)
     - Forwards vote + cfrags to TEE
     - TEE decrypts and processes vote
     - Returns new encrypted state
  3. Listener receives result and **updates contract state on BSC Testnet** using admin private key
- Displays a_ratio and a_funds_ratio when `total_votes % 5 == 0` (if revealed by TEE)
- **Tracks history per market** and saves to `a_ratio_history_{marketId}.json` for frontend visualization

**Expected Output:**

```
============================================================
SMART CONTRACT EVENT LISTENER
============================================================
✅ Connected to BSC Testnet
   Chain ID: 97
   Latest block: 25832156
✅ Contract loaded: 0x...
   Admin: 0x...
   Total markets: 2
   Loading historical data for markets...

👂 Listening for VoteSubmitted events on BSC Testnet...
   Press Ctrl+C to stop
```

**Keep this terminal running.**

### Step 6: Start Frontend API

**Create a `.env` file** (if not already created):

```bash
ADMIN_PRIVATE_KEY=your_admin_private_key_here
```

**Start the API:**

```bash
python frontend_api.py
```

**What this does:**

- Starts FastAPI server on `http://127.0.0.1:3001`
- Provides REST API for the web frontend
- Connects to **BSC Testnet** for all blockchain operations
- Handles vote submission with automatic encryption
- Manages finish/distribute workflow with batching for large voter counts
- **Uses admin private key** for contract state updates

**Keep this terminal running.**

### Step 7: Start Web Frontend

**New terminal:**

```bash
cd front-end
npm install  # First time only
npm run dev
```

**Access the frontend:**

Open your browser to `http://localhost:3000/markets.html` (Market List Page)

**Features:**

- **Polymarket-style market listing** page showing all available markets
- **MetaMask wallet integration** for authentication and transactions
- **Connect wallet** button in header showing address and balance when connected
- **Auto-detect admin status** based on connected wallet
- **Market cards** with title, description, volume, and status
- **Click any market** to navigate to the voting page
- **Dark theme** with teal blue accents
- **Real-time chart** (per market) showing A-ratio and A-funds-ratio over time
- **Vote submission** using connected MetaMask wallet
- **Token symbol display** when creating markets
- **Back button** to return to market list
- **Finish prediction** button (only visible to admin)
- **Claim payout** button for winners when market is finished

### Step 8: Connect MetaMask Wallet

**⚠️ IMPORTANT:** Configure MetaMask for BSC Testnet first!

**Add BSC Testnet to MetaMask:**

1. Open MetaMask
2. Click network dropdown → "Add Network"
3. Enter these details:
   - **Network Name**: BSC Testnet
   - **RPC URL**: https://data-seed-prebsc-1-s1.binance.org:8545/
   - **Chain ID**: 97
   - **Currency Symbol**: BNB
   - **Block Explorer**: https://testnet.bscscan.com/

**Connect to the Frontend:**

1. Open `http://localhost:3000/markets.html`
2. Click **"Connect Wallet"** button in the header
3. Approve the connection in MetaMask
4. Your wallet address and token balance will appear in the header
5. If you're the admin, you'll see the "Create Market" section

**Note:** The frontend automatically detects if you're the admin (deployer) and shows admin-only features.

### Step 9: Submit Votes (Web UI or Script)

#### Option A: Use Web Interface (Recommended)

1. **Connect your MetaMask wallet** (see Step 8)
2. Ensure you have:
   - BNB for gas fees (BSC Testnet)
   - Payment tokens (USDC/DAI/etc.) for the specific market
3. Open `http://localhost:3000/markets.html` to see all markets
4. Click on a market card to enter the voting page
5. Enter bet amount (e.g., 100 USDC)
6. Choose Option A or B
7. Click "Submit Vote"
8. **Approve the transaction in MetaMask** (2 transactions: token approval + vote)
9. Watch the chart update every 5 votes!

**Features:**
- **Token approval**: Automatically prompts to approve token spending
- **Duplicate vote prevention**: Checks if you've already voted
- **Real-time balance**: Shows your token balance
- **Error handling**: Clear error messages for failed transactions
- **Claim payouts**: After market finishes, winners can claim their share

#### Option B: Use Python Script

**⚠️ IMPORTANT:** Configure your wallet private key first!

**Create a `.env` file** or provide private key when prompted:

```bash
python submit_vote_to_contract.py
```

The script will:
- Connect to **BSC Testnet**
- Load your wallet from private key
- Show available markets
- Let you select market, amount, and option
- Submit the vote on BSC Testnet

**Note:** This method requires you to have BNB for gas fees and payment tokens in your wallet.

### Step 10: Automated Voting (Optional - For Testing)

**⚠️ Note:** This feature is not recommended for BSC Testnet testing as it requires multiple funded wallets with tokens. Use MetaMask web interface instead.

### Step 11: Finish Betting and Calculate Payouts

#### Option A: Use Web Interface (Recommended)

**Admin only:**

1. Connect your **admin wallet** via MetaMask
2. Navigate to the market you want to finish
3. Click the "🏁 Finish Prediction" button (only visible to admin)
4. Select the winning option (A or B)
5. Click "Confirm & Distribute"
6. **Approve all transactions in MetaMask**:
   - Transaction 1: Close betting
   - Transaction 2: Set payouts (may be batched)
7. Wait for confirmation on BSC Testnet
8. Market is now finished, winners can claim!

**Note:** With many voters, payouts are automatically batched in groups of 50 to avoid gas limits.

#### Option B: Use Python Script

**⚠️ IMPORTANT:** Requires admin private key in `.env` file!

```bash
python finish_and_distribute.py
```

The script will:
- Connect to **BSC Testnet**
- Use admin private key to send transactions
- Close betting on the selected market
- Calculate payouts via TEE
- Set payouts in contract (with automatic batching)

**Payout Calculation:**

- Winners split the total pool proportionally to their stakes
- Formula: `payout = (your_stake / total_winner_stakes) × total_pool`
- Losers get 0

### Step 12: Claim Winnings

#### Option A: Use Web Interface (Recommended)

**Winners only:**

1. Connect your wallet via MetaMask (the one you voted with)
2. Navigate to the finished market
3. If you're a winner, you'll see:
   - Your claimable amount
   - "Claim Payout" button
   - Claim status (claimed/unclaimed)
4. Click "Claim Payout"
5. **Approve the transaction in MetaMask**
6. Tokens will be transferred to your wallet!

**Features:**
- **Auto-detection**: Shows claim info only if you're a winner
- **Claim status**: Shows if you've already claimed
- **Real-time balance**: Updates after claiming

#### Option B: Use Python Script

**⚠️ IMPORTANT:** Requires your wallet private key!

```bash
python claim_payout.py
```

The script will:
- Connect to **BSC Testnet**
- Load your wallet from private key (from `.env` or prompt)
- Show markets where you have unclaimed payouts
- Let you claim your winnings
- Transaction sent on BSC Testnet

## Project Structure

```
private-market-prediction/
├── tee.py                          # Mock TEE service (FastAPI) with signature
├── kd/
│   ├── kd.py                       # Key distribution setup
│   ├── umbral_state.json          # Generated master keys & kfrags
│   └── tee_signing_key.json       # TEE Ethereum signing key (auto-generated)
├── nodes/
│   ├── node.py                     # Individual node implementation
│   └── run_nodes.py               # Starts 7 threshold nodes
├── contracts/
│   ├── PrivateBetting.sol         # Multi-market smart contract (ERC20)
│   └── MockUSDC.sol               # Test ERC20 token
├── scripts/
│   ├── deploy-with-tee.js         # Deploy with TEE and create default market
│   ├── export-abi.js              # Export contract ABI
│   └── test-contract.js           # Contract testing script
├── front-end/                      # Web frontend (Vite + TypeScript)
│   ├── src/
│   │   ├── main.ts                # Market voting page logic
│   │   ├── markets.ts             # Market list page logic
│   │   └── style.css              # Dark theme with teal blue
│   ├── index.html                 # Market voting page (with ?marketId)
│   ├── markets.html               # Market list page (home)
│   ├── package.json               # Frontend dependencies
│   └── README.md                  # Frontend docs
├── contract_listener.py            # Event listener & history tracker (multi-market)
├── frontend_api.py                # Backend API with admin auth
├── submit_vote_to_contract.py     # CLI vote submission (market selection)
├── auto_vote.py                   # Automated voting script (market targeting)
├── finish_and_distribute.py       # Admin settlement (market selection)
├── claim_payout.py                # Winner claim (market selection)
├── a_ratio_history_{id}.json      # Per-market ratio history
├── contract-abi.json              # Contract ABI
├── token-abi.json                 # Token ABI
├── hardhat.config.js              # Hardhat configuration
├── package.json                    # Node.js dependencies
├── README.md                       # This file
├── ERC20_MIGRATION.md             # ERC20 migration guide
├── MULTI_MARKET_CHANGES.md        # Multi-market migration docs
└── FRONTEND_SETUP.md              # Detailed frontend guide
```

## Features

### ERC20 Token Support

- **Per-market payment tokens** - Each market can use different ERC20 tokens (USDC, DAI, etc.)
- **Token address specified** when creating a market
- **Automatic token approval** in all Python scripts and frontend
- **Token symbol display** when creating markets (fetched from blockchain)
- **Real-time balance tracking** for connected wallets
- **Multi-token support** - Different markets can use different tokens

### Multi-Market Architecture

- **Single contract handles multiple markets** - No need to deploy per market
- **Admin creates markets** via MetaMask wallet
- **Market struct** with id, title, description, state, status, volume, timestamp, **and payment token address**
- **Independent market states** - Each market has its own encrypted state and payouts
- **Market-specific history** - Separate ratio history files per market
- **Polymarket-style UI** - Browse all markets on landing page

### Web Frontend

- **MetaMask wallet integration** - No predefined accounts, real wallet interaction
- **Connect/disconnect wallet** - Persistent connection with auto-reconnect
- **Wallet info display** - Shows connected address (truncated) and token balance
- **Admin auto-detection** - Features appear based on connected wallet
- **Two-page structure**: Market list (home) + Market voting (per market)
- **Market cards** showing title, description, volume, status, creation date
- **Dark theme** with teal blue and cyan accents
- **Dual-metric visualization**: A-ratio (vote %) and A-funds-ratio (funds %)
- **Real-time chart** with Chart.js showing historical trends per market
- **Token symbol fetching** when creating markets
- **Duplicate vote prevention** - Checks if user already voted
- **Claim functionality** - Winners can claim payouts directly from UI
- **Network detection** - Prompts to switch to BSC Testnet if on wrong network
- **Error handling** - Clean error messages for failed transactions
- **Skeleton loading** - Shows loading state while fetching data
- **Responsive design** with full-width chart display
- **Navigation** between market list and voting pages

### Performance Optimizations

- **Batched payouts**: Automatically splits large payout arrays into 50-address batches
- **Gas optimization**: Each batch uses 10M gas limit
- **Handles unlimited voters**: No more "out of gas" errors with many participants
- **Smart chart updates**: Only redraws when data changes (no flickering)

### Admin Features

- **MetaMask-based authentication** - Admin detected by wallet address
- **Address verification** - Backend validates admin address against contract deployer
- **No manual login** - Just connect wallet, admin features appear automatically
- **Market creation** - Create markets with custom title, description, and payment token
- **Finish prediction** - Close betting and distribute payouts
- **Admin-only UI** - Finish button only visible to admin
- **Multi-step workflow** - Automated finish → calculate → set payouts process

### TEE Signature Verification

- **Cryptographic proof** - TEE signs every state transition with Ethereum private key
- **On-chain verification** - Smart contract verifies ECDSA signatures before updating state
- **Signature format** - Uses standard Ethereum signed message format (`\x19Ethereum Signed Message:\n32`)
- **State transition integrity** - Signature covers (prevState, newState) pair
- **TEE address registration** - Contract stores TEE address and rejects unauthorized updates
- **Persistent keys** - TEE signing key saved to `kd/tee_signing_key.json` for consistency
- **No trusted oracle** - Contract cryptographically verifies TEE involvement

## Security Considerations

### Current Implementation

- ✅ Threshold encryption protects against node compromise
- ✅ Forward secrecy prevents historical decryption
- ✅ Byzantine fault tolerance (handles 3 corrupt nodes)
- ✅ Smart contract enforces rules and holds ERC20 tokens
- ✅ Batched payouts prevent gas limit issues
- ✅ ERC20 token approval mechanism for secure transfers
- ✅ **TEE signature verification** - All state updates cryptographically verified
- ✅ **ECDSA signature checking** - Contract verifies TEE signed each transition
- ✅ **TEE address enforcement** - Only valid TEE signatures accepted
- ✅ **MetaMask wallet integration** - Real wallet transactions with user approval
- ✅ **BSC Testnet deployment** - Tested on public testnet
- ✅ **Per-market payment tokens** - Flexible token support
- ✅ **Duplicate vote prevention** - Checks voting status before submission
- ⚠️  TEE is mocked (no hardware isolation)
- ⚠️  Anyone can relay updates (but must have valid TEE signature)
- ⚠️  Testnet deployment (not mainnet-ready)

### Production Requirements

1. **Hardware TEE**
   - Intel SGX, AMD SEV, or ARM TrustZone
   - Remote attestation for verification
   - Sealed storage for keys
   - Hardware-protected signing key

2. **Enhanced Security**
   - Restrict state relay to authorized oracles (optional with signatures)
   - Multi-signature for admin functions
   - Time locks for critical operations
   - Rate limiting for state updates

3. **Economic Security**
   - Node operator bonds
   - Slashing for misbehavior
   - Reward mechanisms for honest operation

4. **Network Deployment**
   - Deploy on testnet (Sepolia, Goerli)
   - Then mainnet with audits
   - Distributed node operators

5. **Token Integration**
   - ✅ Support for any ERC20 token (per market)
   - ✅ Proper token allowance handling in frontend
   - Token balance checks before voting
   - Support for tokens with 6 decimals (real USDC)

6. **Multi-Market Security**
   - Market-specific access controls
   - Admin role management (multi-admin support)
   - Market state isolation (prevent cross-market attacks)
   - Rate limiting for market creation

7. **Wallet Integration**
   - ✅ MetaMask wallet connection with auto-reconnect
   - ✅ Network detection and switching prompts
   - ✅ Transaction approval flow
   - Hardware wallet support (Ledger, Trezor)
   - WalletConnect for mobile wallets

8. **Additional Features**
   - Time-based betting windows per market
   - Minimum/maximum bet limits per market
   - Emergency pause mechanism per market
   - Upgrade mechanisms with proxy pattern
   - Market categories and tagging
   - Market search and filtering
   - Market resolution system with dispute mechanism

## Quick Start (All-in-One)

For the complete setup with web frontend on BSC Testnet:

**Prerequisites:**
- Create `.env` file with `ADMIN_PRIVATE_KEY=your_private_key`
- Add BSC Testnet to MetaMask (see Step 8)
- Have BNB for gas fees and payment tokens (USDC/DAI/etc.)

**Start all services:**

1. **Terminal 1**: `python -m uvicorn tee:app`
2. **Terminal 2**: `cd kd && python kd.py` (paste TEE key, then exit)
3. **Terminal 3**: `cd nodes && python run_nodes.py`
4. **Terminal 4**: `python contract_listener.py` (listens to BSC Testnet)
5. **Terminal 5**: `python frontend_api.py` (connects to BSC Testnet)
6. **Terminal 6**: `cd front-end && npm install && npm run dev`
7. **Browser**: Open `http://localhost:3000/markets.html`
8. **MetaMask**: Click "Connect Wallet" button in header
9. **Create/Vote**: If you're admin, create markets. Otherwise, vote on existing markets!

## Testing

### BSC Testnet Testing

**The project is deployed and running on BSC Testnet. Test by:**

1. **Get BSC Testnet BNB**: Use a faucet like https://testnet.binance.org/faucet-smart
2. **Get payment tokens**: Acquire testnet USDC/DAI or use test tokens
3. **Connect MetaMask**: Add BSC Testnet network to MetaMask
4. **Access frontend**: Open `http://localhost:3000/markets.html`
5. **Test the flow**:
   - Connect wallet
   - Create a market (if admin)
   - Submit votes with your wallet
   - Wait for state updates (listener processes on BSC)
   - Finish prediction (if admin)
   - Claim payouts (if winner)

### What to Expect

- ✅ Single contract deployed on BSC Testnet supporting multiple markets
- ✅ Each market uses its own ERC20 payment token (specified at creation)
- ✅ MetaMask wallet integration for all transactions
- ✅ Admin auto-detected based on connected wallet
- ✅ Users browse markets on Polymarket-style landing page
- ✅ Click market card to navigate to voting page
- ✅ Votes submitted via MetaMask with token approval
- ✅ Listener processes votes automatically on BSC Testnet
- ✅ A-ratio and A-funds-ratio revealed every 5 votes per market
- ✅ Real-time chart updates showing both metrics per market
- ✅ Duplicate vote prevention (checks if already voted)
- ✅ Corrupt nodes don't break the system
- ✅ Automatic batching handles 100+ voters per market
- ✅ Winners can claim their proportional share via UI
- ✅ Losers get 0
- ✅ Contract token balance depletes as winners claim
- ✅ Multiple markets can run simultaneously with different tokens
- ✅ TEE signatures verified on-chain for all state transitions
- ✅ Cryptographic proof of TEE involvement in every update
- ✅ Network detection prompts user to switch to BSC Testnet
- ✅ Clean error handling for failed transactions

## ⚠️ Disclaimer

**This is a proof-of-concept for educational and testing purposes.**

- Do NOT use in production without proper security audits
- The TEE is mocked (no real hardware isolation)
- Currently on testnet (BSC Testnet) - not production-ready
- Test tokens only (no real money at risk)
- No warranties or guarantees provided
- Use at your own risk

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

**Remember**: This is a mock implementation. In production, replace the TEE with actual hardware-isolated trusted execution and implement all security measures.
