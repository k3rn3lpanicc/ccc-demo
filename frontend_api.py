import json
import os
import base64
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from web3 import Web3
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from umbral import PublicKey, encrypt

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RPC_URL = "http://127.0.0.1:8545"
CONTRACT_ADDRESS_FILE = "contract-address.json"
CONTRACT_ABI_FILE = "contract-abi.json"
TOKEN_ABI_FILE = "token-abi.json"
STATE_FILE = "./kd/umbral_state.json"
HISTORY_FILE = "a_ratio_history.json"


def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("utf-8")


def b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("utf-8"))


def load_master_key():
    with open(STATE_FILE, "r") as f:
        data = json.load(f)
    return PublicKey.from_bytes(b64d(data["master_public_key"]))


def aes_encrypt(key: bytes, plaintext: bytes):
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext, None)
    return nonce, ct


@app.get("/api/history/{marketId}")
def get_history(marketId: int):
    try:
        history_file = f"a_ratio_history_{marketId}.json"
        with open(history_file, 'r') as f:
            history = json.load(f)
        return {"success": True, "history": history}
    except FileNotFoundError:
        return {"success": True, "history": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/accounts")
def get_accounts():
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected():
            raise HTTPException(
                status_code=500, detail="Cannot connect to Ethereum node")

        with open(CONTRACT_ADDRESS_FILE, 'r') as f:
            token_address = json.load(f)['tokenAddress']

        with open(TOKEN_ABI_FILE, 'r') as f:
            token_abi = json.load(f)

        token = w3.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=token_abi
        )

        accounts = w3.eth.accounts
        account_list = []

        for i, acc in enumerate(accounts[1:51], 1):
            balance = token.functions.balanceOf(acc).call()
            account_list.append({
                "index": i,
                "address": acc,
                "balance": float(w3.from_wei(balance, 'ether'))
            })

        return {"success": True, "accounts": account_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/markets")
def get_markets():
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected():
            raise HTTPException(
                status_code=500, detail="Cannot connect to Ethereum node")

        with open(CONTRACT_ADDRESS_FILE, 'r') as f:
            contract_address = json.load(f)['address']

        with open(CONTRACT_ABI_FILE, 'r') as f:
            contract_abi = json.load(f)

        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=contract_abi
        )

        market_count = contract.functions.marketCount().call()
        markets = []

        for market_id in range(market_count):
            market = contract.functions.getMarket(market_id).call()
            markets.append({
                "marketId": market[0],
                "title": market[1],
                "description": market[2],
                "encryptedState": market[3],
                "status": market[4],
                "bettingFinished": market[5],
                "createdAt": market[6],
                "totalVolume": float(w3.from_wei(market[7], 'ether'))
            })

        return {"success": True, "markets": markets}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/markets/{marketId}")
def get_market(marketId: int):
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected():
            raise HTTPException(
                status_code=500, detail="Cannot connect to Ethereum node")

        with open(CONTRACT_ADDRESS_FILE, 'r') as f:
            contract_address = json.load(f)['address']

        with open(CONTRACT_ABI_FILE, 'r') as f:
            contract_abi = json.load(f)

        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=contract_abi
        )

        market = contract.functions.getMarket(marketId).call()
        
        return {
            "success": True,
            "market": {
                "marketId": market[0],
                "title": market[1],
                "description": market[2],
                "encryptedState": market[3],
                "status": market[4],
                "bettingFinished": market[5],
                "createdAt": market[6],
                "totalVolume": float(w3.from_wei(market[7], 'ether'))
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CreateMarketRequest(BaseModel):
    title: str
    description: str
    adminAddress: str


@app.post("/api/markets/create")
def create_market(req: CreateMarketRequest):
    try:
        import requests as req_lib
        
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected():
            raise HTTPException(
                status_code=500, detail="Cannot connect to Ethereum node")

        with open(CONTRACT_ADDRESS_FILE, 'r') as f:
            contract_address = json.load(f)['address']

        with open(CONTRACT_ABI_FILE, 'r') as f:
            contract_abi = json.load(f)

        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=contract_abi
        )

        # Verify admin
        admin_address = contract.functions.admin().call()
        input_address = Web3.to_checksum_address(req.adminAddress)
        
        if admin_address.lower() != input_address.lower():
            raise HTTPException(status_code=403, detail="Not authorized: Only admin can create markets")

        # Get initial encrypted state from TEE
        response = req_lib.get("http://127.0.0.1:8000/initialize_state", timeout=10)
        response.raise_for_status()
        result = response.json()

        if not result.get("success"):
            raise HTTPException(status_code=500, detail="TEE initialization failed")

        initial_state = result["encrypted_state"]

        # Create market (use the verified admin address)
        tx_hash = contract.functions.createMarket(
            req.title,
            req.description,
            initial_state
        ).transact({
            'from': input_address,
            'gas': 2000000
        })

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt['status'] == 1:
            # Get the market ID from the event
            market_count = contract.functions.marketCount().call()
            market_id = market_count - 1

            return {
                "success": True,
                "marketId": market_id,
                "txHash": tx_hash.hex()
            }
        else:
            raise HTTPException(status_code=500, detail="Transaction failed")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/status")
def get_admin_status():
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected():
            raise HTTPException(
                status_code=500, detail="Cannot connect to Ethereum node")

        with open(CONTRACT_ADDRESS_FILE, 'r') as f:
            contract_address = json.load(f)['address']

        with open(CONTRACT_ABI_FILE, 'r') as f:
            contract_abi = json.load(f)

        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=contract_abi
        )

        admin_address = contract.functions.admin().call()

        return {
            "success": True,
            "adminAddress": admin_address
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class VerifyAdminRequest(BaseModel):
    address: str


@app.post("/api/admin/verify")
def verify_admin(req: VerifyAdminRequest):
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected():
            raise HTTPException(
                status_code=500, detail="Cannot connect to Ethereum node")

        with open(CONTRACT_ADDRESS_FILE, 'r') as f:
            contract_address = json.load(f)['address']

        with open(CONTRACT_ABI_FILE, 'r') as f:
            contract_abi = json.load(f)

        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=contract_abi
        )

        admin_address = contract.functions.admin().call()
        input_address = Web3.to_checksum_address(req.address)

        is_admin = admin_address.lower() == input_address.lower()

        return {
            "success": True,
            "isAdmin": is_admin,
            "adminAddress": admin_address if is_admin else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class VoteRequest(BaseModel):
    marketId: int
    accountIndex: int
    betAmount: float
    betOn: str


@app.post("/api/vote")
def submit_vote(vote: VoteRequest):
    try:
        if vote.betOn not in ["A", "B"]:
            raise HTTPException(
                status_code=400, detail="betOn must be 'A' or 'B'")

        if vote.betAmount <= 0:
            raise HTTPException(
                status_code=400, detail="betAmount must be positive")

        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected():
            raise HTTPException(
                status_code=500, detail="Cannot connect to Ethereum node")

        accounts = w3.eth.accounts
        if vote.accountIndex < 1 or vote.accountIndex > len(accounts) - 1:
            raise HTTPException(
                status_code=400, detail="Invalid account index")

        voter = accounts[vote.accountIndex]
        bet_amount = w3.to_wei(vote.betAmount, 'ether')

        with open(CONTRACT_ADDRESS_FILE, 'r') as f:
            contract_info = json.load(f)
            contract_address = contract_info['address']
            token_address = contract_info['tokenAddress']

        with open(CONTRACT_ABI_FILE, 'r') as f:
            contract_abi = json.load(f)

        with open(TOKEN_ABI_FILE, 'r') as f:
            token_abi = json.load(f)

        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=contract_abi
        )

        token = w3.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=token_abi
        )

        vote_data = {
            voter: {
                "bet_amount": bet_amount,
                "bet_on": vote.betOn
            }
        }

        master_public_key = load_master_key()
        plaintext = json.dumps(vote_data).encode("utf-8")
        sym_key = os.urandom(32)
        nonce, sym_ciphertext = aes_encrypt(sym_key, plaintext)
        capsule, encrypted_sym_key = encrypt(
            master_public_key, sym_key + nonce)

        vote_ciphertext_b64 = b64e(sym_ciphertext)
        encrypted_sym_key_b64 = b64e(encrypted_sym_key)
        capsule_b64 = b64e(bytes(capsule))

        # Approve token transfer
        approve_tx = token.functions.approve(contract_address, bet_amount).transact({
            'from': voter,
            'gas': 100000
        })
        w3.eth.wait_for_transaction_receipt(approve_tx)

        tx_hash = contract.functions.vote(
            vote.marketId,
            vote_ciphertext_b64,
            encrypted_sym_key_b64,
            capsule_b64,
            bet_amount
        ).transact({
            'from': voter,
            'gas': 3000000
        })

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt['status'] == 1:
            return {
                "success": True,
                "txHash": tx_hash.hex(),
                "blockNumber": receipt['blockNumber'],
                "gasUsed": receipt['gasUsed']
            }
        else:
            raise HTTPException(status_code=500, detail="Transaction failed")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class FinishRequest(BaseModel):
    marketId: int


@app.post("/api/finish")
def finish_betting(req: FinishRequest):
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected():
            raise HTTPException(
                status_code=500, detail="Cannot connect to Ethereum node")

        with open(CONTRACT_ADDRESS_FILE, 'r') as f:
            contract_address = json.load(f)['address']

        with open(CONTRACT_ABI_FILE, 'r') as f:
            contract_abi = json.load(f)

        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=contract_abi
        )

        accounts = w3.eth.accounts
        admin = accounts[0]

        tx_hash = contract.functions.finishBetting(req.marketId).transact({
            'from': admin,
            'gas': 1000000
        })

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt['status'] == 1:
            return {
                "success": True,
                "txHash": tx_hash.hex(),
                "blockNumber": receipt['blockNumber']
            }
        else:
            raise HTTPException(status_code=500, detail="Transaction failed")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CalculatePayoutsRequest(BaseModel):
    marketId: int
    winningOption: str


@app.post("/api/calculate-payouts")
def calculate_payouts(req: CalculatePayoutsRequest):
    try:
        import requests as req_lib

        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected():
            raise HTTPException(
                status_code=500, detail="Cannot connect to Ethereum node")

        with open(CONTRACT_ADDRESS_FILE, 'r') as f:
            contract_address = json.load(f)['address']

        with open(CONTRACT_ABI_FILE, 'r') as f:
            contract_abi = json.load(f)

        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=contract_abi
        )

        current_state = contract.functions.getCurrentState(req.marketId).call()

        response = req_lib.post(
            "http://127.0.0.1:8000/finish",
            json={
                "current_state": current_state,
                "winning_option": req.winningOption
            },
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get(
                "error", "TEE calculation failed"))

        return {
            "success": True,
            "payouts": result["payouts"],
            "total_pool": result["total_pool"],
            "total_winners": result["total_winners"],
            "total_losers": result["total_losers"]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SetPayoutsRequest(BaseModel):
    marketId: int
    payouts: list


@app.post("/api/set-payouts")
def set_payouts(req: SetPayoutsRequest):
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected():
            raise HTTPException(
                status_code=500, detail="Cannot connect to Ethereum node")

        with open(CONTRACT_ADDRESS_FILE, 'r') as f:
            contract_address = json.load(f)['address']

        with open(CONTRACT_ABI_FILE, 'r') as f:
            contract_abi = json.load(f)

        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=contract_abi
        )

        accounts = w3.eth.accounts
        admin = accounts[0]

        payouts = [p for p in req.payouts if p['payout'] > 0]

        all_addresses = [payout['wallet'] for payout in payouts]
        all_amounts = [int(payout['payout']) for payout in payouts]  # Convert to int

        BATCH_SIZE = 20
        total_batches = (len(all_addresses) + BATCH_SIZE - 1) // BATCH_SIZE

        tx_hashes = []

        for i in range(0, len(all_addresses), BATCH_SIZE):
            batch_addresses = all_addresses[i:i + BATCH_SIZE]
            batch_amounts = all_amounts[i:i + BATCH_SIZE]
            is_last_batch = (i + BATCH_SIZE) >= len(all_addresses)

            print(
                f"Setting payouts batch {i//BATCH_SIZE + 1}/{total_batches} ({len(batch_addresses)} addresses)")

            tx_hash = contract.functions.setPayouts(
                req.marketId,
                batch_addresses,
                batch_amounts,
                is_last_batch
            ).transact({
                'from': admin,
                'gas': 10000000
            })

            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

            if receipt['status'] != 1:
                raise HTTPException(
                    status_code=500, detail=f"Transaction failed in batch {i//BATCH_SIZE + 1}")

            tx_hashes.append(tx_hash.hex())

        return {
            "success": True,
            "txHashes": tx_hashes,
            "batches": total_batches,
            "totalPayouts": len(all_addresses)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=3001)
