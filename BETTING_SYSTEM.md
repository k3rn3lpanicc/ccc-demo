# Private Betting System with Threshold Encryption

This system implements a privacy-preserving betting system where:

- The betting state is encrypted and stored (simulating a smart contract)
- Users submit encrypted votes through decentralized nodes
- A TEE (Trusted Execution Environment) processes votes and updates the state
- Each state update uses a fresh symmetric key for forward secrecy
- Threshold encryption ensures no single node can decrypt votes

## Architecture

```
User → Node → [Collect cfrags from all nodes] → TEE → New Encrypted State
```

### Components

1. **TEE (tee.py)**:
   - Holds the private key (Bob's secret key)
   - Decrypts votes using threshold encryption
   - Updates betting state
   - Re-encrypts state with new symmetric key

2. **Nodes (nodes/node.py)**:
   - Hold key fragments (kfrags)
   - Provide re-encryption service
   - Proxy user requests to TEE
   - Verify cfrags before forwarding

3. **Users**:
   - Encrypt their votes with master public key
   - Submit to any node
   - Receive confirmation of vote processing

## Betting State Structure

```json
{
  "a_ratio": 0.6,  // Ratio of A votes to total votes (or null if no votes)
  "votes": {
    "0xWalletAddress1": {
      "bet_amount": 100,
      "bet_on": "A"
    },
    "0xWalletAddress2": {
      "bet_amount": 200,
      "bet_on": "B"
    }
  }
}
```

## Setup Instructions

### 1. Start the TEE

```bash
python tee.py
```

Copy the TEE Public Key that is printed.

### 2. Generate Keys (First Time Only)

```bash
cd kd
python kd.py
```

Paste the TEE Public Key when prompted.

### 3. Start the Nodes

```bash
cd nodes
python run_nodes.py
```

This will start 7 nodes on ports 5000-5006 (threshold = 4).

### 4. Initialize the Betting State

```bash
python initialize_betting.py
```

This creates an empty encrypted state and saves it to `contract_state.txt`.
In production, this encrypted state would be stored in the smart contract.

## Usage

### Cast a Vote

```bash
python cast_vote.py
```

You will be prompted for:

- Wallet address (e.g., 0x123...)
- Bet amount (e.g., 100)
- Bet choice (A or B)

The script will:

1. Encrypt your vote with AES-GCM
2. Encrypt the symmetric key with Umbral (threshold encryption)
3. Submit to a node
4. Node collects cfrags from all nodes
5. Node forwards to TEE
6. TEE decrypts, processes vote, updates state
7. TEE returns new encrypted state
8. Script saves new state to `contract_state.txt`

### View Current State (Debug)

```bash
python view_state.py
```

This decrypts and displays the current betting state using the TEE's private key.

## Security Features

### 1. Threshold Encryption

- Vote encryption keys are split among 7 nodes
- Requires 4 nodes (threshold) to decrypt
- No single node can decrypt votes alone

### 2. Forward Secrecy

- Each state update uses a NEW symmetric key
- Old keys are discarded
- Even if one key is compromised, past/future states remain secure

### 3. Privacy

- Individual votes are encrypted
- Only TEE can decrypt votes
- State ratio is calculated inside TEE
- Nobody outside TEE sees individual votes

### 4. Verification

- Nodes verify cfrags from other nodes
- Prevents corrupted nodes from affecting decryption
- TEE verifies threshold is met

## API Endpoints

### TEE Endpoints

**GET /initialize_state**

- Initializes empty betting state
- Returns encrypted state for contract storage

**POST /submit**

- Processes a vote
- Input: encrypted vote, cfrags, current state
- Output: new encrypted state

### Node Endpoints

**POST /submit_vote**

- User-facing endpoint for vote submission
- Collects cfrags from all nodes
- Forwards to TEE
- Returns result to user

**POST /reencrypt**

- Internal endpoint for nodes
- Re-encrypts using key fragment
- Returns cfrag

## State Flow

```
1. Initialize:
   TEE → Empty State → Encrypt with Key1 → Contract

2. User Votes:
   User → Encrypt Vote → Node
   Node → Collect cfrags → Forward to TEE
   TEE → Decrypt Vote → Decrypt State (Key1)
   TEE → Update State → Encrypt with Key2 → Return
   Node → Update Contract with new encrypted state

3. Another User Votes:
   User → Encrypt Vote → Node
   Node → Collect cfrags → Forward to TEE
   TEE → Decrypt Vote → Decrypt State (Key2)  # Note: Key1 is forgotten
   TEE → Update State → Encrypt with Key3 → Return
   Node → Update Contract with new encrypted state
```

## Testing Scenario

### Manual Testing

```bash
# Terminal 1: Start TEE
python tee.py

# Terminal 2: Start nodes (after key generation)
cd nodes
python run_nodes.py

# Terminal 3: Initialize and cast votes
python initialize_betting.py
python cast_vote.py  # Vote A
python cast_vote.py  # Vote B
python view_state.py  # Check results
python finish_betting.py  # Calculate payouts
```

### Automated Testing

```bash
# Run complete flow test
python test_betting_flow.py
```

This will:
1. Initialize empty state
2. Cast 5 votes (3 for A, 2 for B)
3. Ask you to choose winner
4. Calculate and display payouts
5. Save payouts to payouts.json

## Production Integration

In production:

1. Replace `contract_state.txt` with actual smart contract storage
2. Nodes fetch current state from blockchain
3. Nodes submit new state to blockchain transaction
4. Smart contract verifies TEE signature (optional)
5. Add authentication for wallet ownership
6. Add betting periods/deadlines
7. Add payout calculation after betting closes

## Payout Calculation

When betting finishes:

1. **Winners Split the Pool**: Winners receive payouts proportional to their bets
   - If Alice bet 100 on A and Bob bet 200 on A (total 300)
   - And total pool is 500
   - Alice gets: (100/300) × 500 = 166.67
   - Bob gets: (200/300) × 500 = 333.33

2. **Losers Get Nothing**: Those who bet on the losing option receive 0

3. **Edge Case**: If no one bet on the winning option, everyone gets their money back

### Example

```
Initial bets:
- Alice: 100 on A
- Bob: 200 on A  
- Charlie: 150 on B
- Dave: 50 on B

Total pool: 500
A total: 300
B total: 200

If A wins:
- Alice: (100/300) × 500 = 166
- Bob: (200/300) × 500 = 333
- Charlie: 0
- Dave: 0

If B wins:
- Alice: 0
- Bob: 0
- Charlie: (150/200) × 500 = 375
- Dave: (50/200) × 500 = 125
```

## Notes

- Each wallet can only vote once (enforced by TEE)
- State updates are atomic
- TEE never stores symmetric keys permanently
- Nodes cannot decrypt or see vote contents
- System continues to work even if 3 nodes fail (threshold = 4/7)
- Payout calculation happens in TEE - results are public (unencrypted)
- Smart contract can use payout list to allow withdrawals
