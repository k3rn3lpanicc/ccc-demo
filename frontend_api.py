"""
FastAPI server to provide data and voting endpoints for the frontend
"""
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

# Enable CORS for frontend
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

@app.get("/api/history")
def get_history():
    """Get a_ratio history"""
    try:
        with open(HISTORY_FILE, 'r') as f:
            history = json.load(f)
        return {"success": True, "history": history}
    except FileNotFoundError:
        return {"success": True, "history": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/accounts")
def get_accounts():
    """Get available Hardhat accounts"""
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected():
            raise HTTPException(status_code=500, detail="Cannot connect to Ethereum node")
        
        accounts = w3.eth.accounts
        account_list = []
        
        # Skip first account (admin/deployer), get up to 50 accounts
        for i, acc in enumerate(accounts[1:51], 1):
            balance = w3.from_wei(w3.eth.get_balance(acc), 'ether')
            account_list.append({
                "index": i,
                "address": acc,
                "balance": float(balance)
            })
        
        return {"success": True, "accounts": account_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/contract/status")
def get_contract_status():
    """Get contract status and info"""
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected():
            raise HTTPException(status_code=500, detail="Cannot connect to Ethereum node")
        
        with open(CONTRACT_ADDRESS_FILE, 'r') as f:
            contract_address = json.load(f)['address']
        
        with open(CONTRACT_ABI_FILE, 'r') as f:
            contract_abi = json.load(f)
        
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=contract_abi
        )
        
        betting_finished = contract.functions.bettingFinished().call()
        contract_balance = w3.eth.get_balance(contract_address)
        
        return {
            "success": True,
            "address": contract_address,
            "bettingFinished": betting_finished,
            "balance": float(w3.from_wei(contract_balance, 'ether'))
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class VoteRequest(BaseModel):
    accountIndex: int
    betAmount: float
    betOn: str

@app.post("/api/vote")
def submit_vote(vote: VoteRequest):
    """Submit a vote to the contract"""
    try:
        if vote.betOn not in ["A", "B"]:
            raise HTTPException(status_code=400, detail="betOn must be 'A' or 'B'")
        
        if vote.betAmount <= 0:
            raise HTTPException(status_code=400, detail="betAmount must be positive")
        
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected():
            raise HTTPException(status_code=500, detail="Cannot connect to Ethereum node")
        
        accounts = w3.eth.accounts
        if vote.accountIndex < 1 or vote.accountIndex > len(accounts) - 1:
            raise HTTPException(status_code=400, detail="Invalid account index")
        
        voter = accounts[vote.accountIndex]
        bet_amount_wei = w3.to_wei(vote.betAmount, 'ether')
        
        # Load contract
        with open(CONTRACT_ADDRESS_FILE, 'r') as f:
            contract_address = json.load(f)['address']
        
        with open(CONTRACT_ABI_FILE, 'r') as f:
            contract_abi = json.load(f)
        
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=contract_abi
        )
        
        # Encrypt vote
        vote_data = {
            voter: {
                "bet_amount": bet_amount_wei,
                "bet_on": vote.betOn
            }
        }
        
        master_public_key = load_master_key()
        plaintext = json.dumps(vote_data).encode("utf-8")
        sym_key = os.urandom(32)
        nonce, sym_ciphertext = aes_encrypt(sym_key, plaintext)
        capsule, encrypted_sym_key = encrypt(master_public_key, sym_key + nonce)
        
        vote_ciphertext_b64 = b64e(sym_ciphertext)
        encrypted_sym_key_b64 = b64e(encrypted_sym_key)
        capsule_b64 = b64e(bytes(capsule))
        
        # Submit to contract
        tx_hash = contract.functions.vote(
            vote_ciphertext_b64,
            encrypted_sym_key_b64,
            capsule_b64
        ).transact({
            'from': voter,
            'value': bet_amount_wei,
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

@app.post("/api/finish")
def finish_betting():
    """Finish betting period"""
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected():
            raise HTTPException(status_code=500, detail="Cannot connect to Ethereum node")
        
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
        
        tx_hash = contract.functions.finishBetting().transact({
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
    winningOption: str

@app.post("/api/calculate-payouts")
def calculate_payouts(req: CalculatePayoutsRequest):
    """Calculate payouts via TEE"""
    try:
        import requests as req_lib
        
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected():
            raise HTTPException(status_code=500, detail="Cannot connect to Ethereum node")
        
        with open(CONTRACT_ADDRESS_FILE, 'r') as f:
            contract_address = json.load(f)['address']
        
        with open(CONTRACT_ABI_FILE, 'r') as f:
            contract_abi = json.load(f)
        
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=contract_abi
        )
        
        current_state = contract.functions.getCurrentState().call()
        
        # Call TEE
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
            raise HTTPException(status_code=500, detail=result.get("error", "TEE calculation failed"))
        
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
    payouts: list

@app.post("/api/set-payouts")
def set_payouts(req: SetPayoutsRequest):
    """Set payouts in contract with batching to avoid gas limits"""
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected():
            raise HTTPException(status_code=500, detail="Cannot connect to Ethereum node")
        
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
        
        all_addresses = [payout['wallet'] for payout in req.payouts]
        all_amounts = [payout['payout'] for payout in req.payouts]
        
        # Batch payouts to avoid gas limits (50 per batch)
        BATCH_SIZE = 50
        total_batches = (len(all_addresses) + BATCH_SIZE - 1) // BATCH_SIZE
        
        tx_hashes = []
        
        for i in range(0, len(all_addresses), BATCH_SIZE):
            batch_addresses = all_addresses[i:i + BATCH_SIZE]
            batch_amounts = all_amounts[i:i + BATCH_SIZE]
            is_last_batch = (i + BATCH_SIZE) >= len(all_addresses)
            
            print(f"Setting payouts batch {i//BATCH_SIZE + 1}/{total_batches} ({len(batch_addresses)} addresses)")
            
            tx_hash = contract.functions.setPayouts(
                batch_addresses,
                batch_amounts,
                is_last_batch
            ).transact({
                'from': admin,
                'gas': 10000000
            })
            
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt['status'] != 1:
                raise HTTPException(status_code=500, detail=f"Transaction failed in batch {i//BATCH_SIZE + 1}")
            
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
