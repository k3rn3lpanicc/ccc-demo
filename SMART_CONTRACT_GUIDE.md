# Smart Contract Integration Guide

## Overview

The betting system now includes a Solidity smart contract that manages:

- Encrypted vote submissions with funds
- State updates after vote processing
- Admin-controlled betting finish
- Automated payout distribution

## Architecture

```
User → Smart Contract → Event → Listener → Nodes → TEE → Updated State → Contract
                                     ↓
                                 VoteSubmitted Event
                                     ↓
                          Python Listener Script
                                     ↓
                         Collect cfrags from nodes
                                     ↓
                            Forward to TEE
                                     ↓
                         Update contract state
```

## Setup

### 1. Install Dependencies

```bash
npm install
```

### 2. Compile Contract

```bash
npx hardhat compile
node scripts/export-abi.js
```

This creates:

- `contract-abi.json` - Contract ABI for Python scripts

### 3. Start Hardhat Node

```bash
# Terminal 1
npx hardhat node
```

This starts a local Ethereum node at `http://127.0.0.1:8545`

### 4. Deploy Contract

```bash
# Terminal 2
npx hardhat run scripts/deploy.js --network localhost
```

This creates `contract-address.json` with the deployed contract address.

### 5. Start Services

```bash
# Terminal 3: TEE
python tee.py

# Terminal 4: Nodes
cd nodes
python run_nodes.py

# Terminal 5: Contract Listener
pip install web3
python contract_listener.py
```

## Smart Contract Functions

### User Functions

**`vote(encryptedVote, encryptedSymKey, capsule)`** - Payable

- Submit an encrypted vote with ETH
- Emits `VoteSubmitted` event
- Funds are held in contract until payout

**`claimPayout()`**

- Winners claim their calculated payouts
- Can only be called after admin sets payouts
- Transfers ETH to winner

**`getCurrentState()`** - View

- Get current encrypted state
- Used by nodes/TEE for processing

**`getPayoutAmount(address)`** - View

- Check payout amount for an address

### Admin Functions

**`finishBetting()`**

- Close betting period
- Only admin can call
- Emits `BettingFinished` event

**`setPayouts(addresses[], amounts[])`**

- Set calculated payouts from TEE
- Only admin can call
- Must be called after `finishBetting()`

**`updateState(newState)`**

- Update encrypted state after vote processing
- In production, should be restricted to oracle/nodes

## Contract Flow

### 1. Deployment

```javascript
const contract = await PrivateBetting.deploy(initialEncryptedState);
```

### 2. User Votes

```javascript
await contract.vote(
  "base64_encrypted_vote",
  "base64_encrypted_key", 
  "base64_capsule",
  { value: ethers.parseEther("1.0") }
);
```

### 3. Event Processing

The `contract_listener.py` script:

1. Detects `VoteSubmitted` event
2. Gets current state from contract
3. Submits to nodes for threshold decryption
4. Receives new state from TEE
5. Updates contract state

### 4. Finish Betting

```javascript
await contract.finishBetting(); // Admin only
```

### 5. Calculate Payouts

Off-chain (TEE):

```python
response = requests.post(
  "http://127.0.0.1:8000/finish",
  json={
    "current_state": contract_state,
    "winning_option": "A"
  }
)
payouts = response.json()['payouts']
```

### 6. Set Payouts

```javascript
const winners = ["0xAddr1", "0xAddr2"];
const amounts = [parseEther("1.5"), parseEther("3.0")];
await contract.setPayouts(winners, amounts);
```

### 7. Users Claim

```javascript
await contract.claimPayout(); // Each winner calls this
```

## Events

### VoteSubmitted

```solidity
event VoteSubmitted(
    address indexed voter,
    string encryptedVote,
    string encryptedSymKey,
    string capsule,
    uint256 amount
);
```

Emitted when a user casts a vote.

### BettingFinished

```solidity
event BettingFinished(string winningOption, string finalState);
```

Emitted when admin closes betting.

### PayoutsSet

```solidity
event PayoutsSet(uint256 totalWinners, uint256 totalPool);
```

Emitted when admin sets calculated payouts.

### StateUpdated

```solidity
event StateUpdated(string newEncryptedState);
```

Emitted when contract state is updated after processing a vote.

### PayoutClaimed

```solidity
event PayoutClaimed(address indexed winner, uint256 amount);
```

Emitted when a winner claims their payout.

## Testing

### Run Contract Tests

```bash
npx hardhat run scripts/test-contract.js --network localhost
```

### Full Integration Test

```bash
# 1. Start all services (Hardhat node, TEE, Nodes, Listener)

# 2. Deploy contract
npx hardhat run scripts/deploy.js --network localhost

# 3. Have users vote (contract_listener will process automatically)

# 4. Admin finishes betting (via ethers.js or web3.py)

# 5. Calculate payouts via TEE

# 6. Admin sets payouts on contract

# 7. Winners claim their payouts
```

## Python Integration

Install web3.py:

```bash
pip install web3
```

Example vote submission from Python:

```python
from web3 import Web3
import json

w3 = Web3(Web3.HTTPProvider('http://127.0.0.1:8545'))

with open('contract-abi.json') as f:
    abi = json.load(f)
    
with open('contract-address.json') as f:
    address = json.load(f)['address']

contract = w3.eth.contract(address=address, abi=abi)

# Submit vote
tx_hash = contract.functions.vote(
    "encrypted_vote_b64",
    "encrypted_key_b64",
    "capsule_b64"
).transact({
    'from': user_address,
    'value': w3.to_wei(1, 'ether')
})

receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
print(f"Vote submitted: {receipt.transactionHash.hex()}")
```

## Security Considerations

### Production Checklist

1. **Oracle Authorization**: Restrict `updateState()` to authorized oracles
2. **Event Verification**: Verify event authenticity before processing
3. **State Validation**: Validate encrypted state format
4. **Payout Verification**: Verify TEE signatures on payouts
5. **Reentrancy Protection**: Already included via CEI pattern
6. **Access Control**: Admin functions properly protected
7. **Time Locks**: Consider adding betting deadlines

### Current Limitations (Development)

- Anyone can call `updateState()` (should be oracle-only)
- No signature verification on TEE responses
- No time-based betting periods
- No minimum/maximum bet limits

## Deployment to Real Network

### 1. Configure Network

Edit `hardhat.config.js`:

```javascript
networks: {
  sepolia: {
    url: process.env.SEPOLIA_URL,
    accounts: [process.env.PRIVATE_KEY]
  }
}
```

### 2. Deploy

```bash
npx hardhat run scripts/deploy.js --network sepolia
```

### 3. Verify Contract

```bash
npx hardhat verify --network sepolia CONTRACT_ADDRESS "INITIAL_STATE"
```

## Troubleshooting

**Contract listener not detecting events**

- Make sure Hardhat node is running
- Verify contract address in `contract-address.json`
- Check contract ABI is exported

**State update fails**

- Ensure listener account has ETH for gas
- Verify nodes and TEE are running
- Check threshold is met (4/7 nodes)

**Payout claim fails**

- Verify payouts are set (`status == PayoutsSet`)
- Check payout amount > 0
- Ensure not already claimed

## Files

- `contracts/PrivateBetting.sol` - Main contract
- `scripts/deploy.js` - Deployment script
- `scripts/test-contract.js` - Contract test
- `scripts/export-abi.js` - Export ABI
- `contract_listener.py` - Event listener & processor
- `hardhat.config.js` - Hardhat configuration
- `contract-address.json` - Deployed address (generated)
- `contract-abi.json` - Contract ABI (generated)

   Quick Start:

  # 1. Compile

     npm run compile

  # 2. Start Hardhat node

     npm run node

  # 3. Deploy

     npm run deploy

  # 4. Start services (TEE, nodes, listener)

     python tee.py
     cd nodes && python run_nodes.py
     python contract_listener.py

  # 5. Test

     npm run test-contract
