# ERC20 Token Migration

## Summary

The Private Market Prediction system has been migrated from native ETH to ERC20 tokens (MockUSDC for testing).

## Changes Made

### Smart Contracts

1. **MockUSDC.sol** (NEW)
   - ERC20 token contract for testing
   - Symbol: USDC
   - 18 decimals (standard for testing)
   - Includes `mint()` function for easy testing
   - Deployer receives 1,000,000 USDC on deployment

2. **PrivateBetting.sol** (UPDATED)
   - Added `IERC20 public token` state variable
   - Constructor now takes `_tokenAddress` parameter
   - `vote()` function:
     - Removed `payable` modifier
     - Added `amount` parameter
     - Uses `token.transferFrom()` instead of receiving ETH
   - `claimPayout()` function:
     - Uses `token.transfer()` instead of sending ETH
   - `getContractBalance()` function:
     - Returns `token.balanceOf(address(this))`
   - Added `getTokenAddress()` helper function

### Deployment

1. **deploy-with-tee.js** (UPDATED)
   - Deploys MockUSDC first
   - Mints 10,000 USDC to accounts 1-50
   - Deploys PrivateBetting with token address
   - Saves both addresses to `contract-address.json`

2. **export-abi.js** (UPDATED)
   - Exports both contract and token ABIs
   - Creates `token-abi.json` file

### Python Scripts

All scripts updated to work with ERC20 tokens:

1. **submit_vote_to_contract.py**
   - Loads token contract
   - Shows USDC balances instead of ETH
   - Calls `token.approve()` before voting
   - Passes amount parameter to `vote()`

2. **auto_vote.py**
   - Updated bet ranges (100-10,000 USDC)
   - Approves tokens before each vote
   - Shows USDC amounts in output

3. **frontend_api.py**
   - Loads token contract
   - Shows USDC balances in account list
   - Approves tokens before voting
   - Updated balance display

4. **contract_listener.py**
   - Shows USDC amounts in event logs

5. **claim_payout.py**
   - Shows USDC balances
   - Token transfer instead of ETH

### Frontend

1. **index.html**
   - Changed "Bet Amount (ETH)" to "Bet Amount (USDC)"
   - Updated default value from 0.1 to 100

2. **main.ts**
   - Shows USDC in account dropdown
   - Shows USDC in contract balance
   - Changed precision from 4 to 2 decimals

## Testing

After migration, test with:

```bash
# 1. Deploy contracts
npx hardhat run scripts/deploy-with-tee.js --network localhost

# 2. Start contract listener
python contract_listener.py

# 3. Submit test vote
python submit_vote_to_contract.py

# 4. Or use automated voting
python auto_vote.py
```

## Key Differences

| Aspect | Before (ETH) | After (USDC) |
|--------|-------------|--------------|
| Transfer | `msg.value` | `transferFrom()` |
| Approval | Not needed | Required before vote |
| Balance | `address.balance` | `token.balanceOf()` |
| Payout | `call{value}()` | `token.transfer()` |
| Default amounts | 0.1 ETH | 100 USDC |
| Test ranges | 0.1-20 ETH | 100-10,000 USDC |

## Notes

- Users must approve the contract to spend their USDC before voting
- The system automatically approves tokens in the Python scripts and frontend
- Real USDC uses 6 decimals, but MockUSDC uses 18 for easier testing
