# Multi-Market Support Implementation

## Overview
Changed from single market to multiple markets in one contract.

## Contract Changes

### Key Modifications:
1. **Removed global state** - Each market has its own state
2. **Added Market struct** with: id, title, description, encryptedState, status, etc.
3. **Added marketCount** counter
4. **Updated all functions** to accept `marketId` parameter
5. **Added `createMarket()`** function for admin
6. **Added `getAllMarketIds()`** and `getMarket()` view functions

### New Data Structures:
```solidity
struct Market {
    uint256 marketId;
    string title;
    string description;
    string encryptedState;
    BettingStatus status;
    bool bettingFinished;
    uint256 createdAt;
    uint256 totalVolume;
}

mapping(uint256 => Market) public markets;
mapping(uint256 => mapping(address => uint256)) public payouts;
mapping(uint256 => mapping(address => bool)) public hasClaimed;
```

## Files That Need Updates

### Backend (Python):
- [ ] `frontend_api.py` - Add market listing, create market, update vote/finish/claim
- [ ] `contract_listener.py` - Handle marketId in events
- [ ] `submit_vote_to_contract.py` - Add market selection
- [ ] `auto_vote.py` - Target specific market
- [ ] `finish_and_distribute.py` - Specify market
- [ ] `claim_payout.py` - Specify market

### Frontend:
- [ ] Create new `market-list` page (home page)
- [ ] Update existing page to be market-specific
- [ ] Add routing between pages
- [ ] Update API calls to include marketId

### TEE:
- [ ] No changes needed (still processes votes the same way)

### Nodes:
- [ ] No changes needed (still handle encryption the same way)

## API Endpoints To Add/Update

### New Endpoints:
- `GET /api/markets` - List all markets
- `POST /api/markets/create` - Admin creates new market
- `GET /api/markets/{id}` - Get specific market details

### Updated Endpoints:
- `POST /api/vote` - Add marketId parameter
- `POST /api/finish` - Add marketId parameter  
- `POST /api/calculate-payouts` - Add marketId parameter
- `POST /api/set-payouts` - Add marketId parameter
- `GET /api/contract/status` - Remove (market-specific now)

## Frontend Pages Structure

```
/ (Home/Market List)
  - Shows all markets in cards
  - Each card shows: title, description, volume, status
  - Click card → navigate to /market/:id

/market/:id (Market Detail/Voting)
  - Current voting page
  - Shows market-specific info
  - Vote submission for this market
```

## Migration Steps

1. ✅ Update smart contract
2. ✅ Update deployment script
3. ✅ Compile contracts
4. [ ] Update frontend API
5. [ ] Update Python scripts
6. [ ] Create market list frontend page
7. [ ] Add routing to frontend
8. [ ] Update contract listener
9. [ ] Test end-to-end
