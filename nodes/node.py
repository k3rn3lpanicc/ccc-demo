import base64
import os
import json
import requests
import time
import random
import threading
from typing import Dict, List, Optional
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from umbral import VerifiedKeyFrag, reencrypt, Capsule, CapsuleFrag, PublicKey, VerificationError
from web3 import Web3

KFRAG_B64 = os.getenv("KFRAG")
CORRUPTED = os.getenv("CORRUPTED", "0") == "1"
NODE_PORT = os.getenv("NODE_PORT")
NODE_ID = int(os.getenv("NODE_ID", "0"))

if not KFRAG_B64:
    raise Exception("SECRET_KEY_SHARE and KFRAG must be set in environment")

kfrag_bytes = base64.b64decode(KFRAG_B64)
kfrag = VerifiedKeyFrag.from_verified_bytes(kfrag_bytes)

STATE_FILE = "../kd/umbral_state.json"
CONTRACT_ADDRESS_FILE = "../contract-address.json"
CONTRACT_ABI_FILE = "../contract-abi.json"
RPC_URL = "http://127.0.0.1:8545"

app = FastAPI()

# Global state for leader election
class NodeState:
    def __init__(self):
        self.node_reputation = {i: {'successes': 0, 'failures': 0, 'weight': 1.0} for i in range(7)}
        self.current_leader = None
        self.leader_elected_at = 0
        self.election_round = 0
        self.processed_events = set()
        self.pending_events = []
        self.is_corrupt = CORRUPTED  # Set from environment variable
        self.leader_timeout = 15  # seconds - leader must process within this time
        self.processing_cooldown = 3  # seconds - wait before processing next event
        self.last_processed_time = 0
        self.is_monitoring = False
        # Voting state
        self.election_in_progress = False
        self.current_votes = {}  # {node_id: proposed_leader}
        self.min_votes_to_tally = 7  # Wait for all votes before tallying
        
    def propose_leader_candidate(self) -> int:
        """Calculate weighted random leader candidate for this node"""
        # Corrupt nodes only vote for themselves
        if self.is_corrupt:
            print(f"💀 CORRUPT Node {NODE_ID} votes for itself!")
            return NODE_ID
        
        weights = [rep['weight'] for rep in self.node_reputation.values()]
        total_weight = sum(weights)
        probabilities = [w / total_weight for w in weights]
        
        candidate = random.choices(range(7), weights=probabilities)[0]
        
        print(f"🗳️  Node {NODE_ID} proposes: Node {candidate}")
        print(f"   Probabilities: {[f'{p:.2%}' for p in probabilities]}")
        return candidate
    
    def start_election(self):
        """Start a new election round"""
        self.election_round += 1
        self.election_in_progress = True
        self.current_votes = {}
        print(f"\n{'='*60}")
        print(f"🗳️  ELECTION ROUND {self.election_round} STARTED")
        print(f"{'='*60}")
    
    def cast_vote(self, voter_id: int, candidate: int):
        """Record a vote for a leader candidate"""
        self.current_votes[voter_id] = candidate
        print(f"✅ Node {voter_id} voted for Node {candidate} ({len(self.current_votes)}/7 votes)")
    
    def tally_votes(self) -> Optional[int]:
        """Tally votes and return winner with most votes (plurality)"""
        if len(self.current_votes) < self.min_votes_to_tally:
            return None
        
        # Count votes
        vote_counts = {}
        for candidate in self.current_votes.values():
            vote_counts[candidate] = vote_counts.get(candidate, 0) + 1
        
        # Find candidate(s) with most votes
        max_votes = max(vote_counts.values())
        candidates_with_max = [c for c, v in vote_counts.items() if v == max_votes]
        
        # If there's a clear winner (no tie)
        if len(candidates_with_max) == 1:
            winner = candidates_with_max[0]
            print(f"\n{'='*60}")
            print(f"🎉 ELECTION RESULT: Node {winner} elected!")
            print(f"   Votes received: {max_votes}/{len(self.current_votes)}")
            print(f"   Vote breakdown: {vote_counts}")
            print(f"{'='*60}\n")
            
            self.current_leader = winner
            self.leader_elected_at = time.time()
            self.election_in_progress = False
            self.current_votes = {}
            return winner
        
        # Tie detected - need re-election
        print(f"\n⚠️  TIE DETECTED! Multiple candidates with {max_votes} votes each")
        print(f"   Tied candidates: {candidates_with_max}")
        print(f"   Vote breakdown: {vote_counts}")
        print(f"   Re-election needed...")
        self.election_in_progress = False
        self.current_votes = {}
        return None
    
    def update_reputation(self, node_id: int, success: bool):
        """Update node reputation"""
        rep = self.node_reputation[node_id]
        if success:
            rep['successes'] += 1
        else:
            rep['failures'] += 1
        
        # Update weight based on success rate
        total = rep['successes'] + rep['failures']
        if total > 0:
            success_rate = rep['successes'] / total
            if success_rate > 0.8:
                rep['weight'] = min(3.0, rep['weight'] + 0.2)
            elif success_rate < 0.3:
                rep['weight'] = max(0.1, rep['weight'] - 0.3)
            else:
                if success_rate > 0.5:
                    rep['weight'] = min(2.0, rep['weight'] + 0.05)
                else:
                    rep['weight'] = max(0.3, rep['weight'] - 0.1)
        
        print(f"📊 Node {node_id}: Success rate={rep['successes']}/{total} ({success_rate:.1%} if total else 0), Weight={rep['weight']:.2f}")
    
    def should_reelect(self) -> bool:
        """Check if we need to trigger reelection"""
        # If no leader and we have pending events, elect one
        if self.current_leader is None and self.pending_events:
            print(f"⚠️  No leader with pending events - triggering election")
            return True
        
        # If we have pending events, check leader timeout
        if self.pending_events:
            oldest_event = self.pending_events[0]
            wait_time = time.time() - oldest_event['detected_at']
            
            if wait_time > self.leader_timeout:
                print(f"⚠️  Leader {self.current_leader} failed to process event in {wait_time:.1f}s")
                print(f"   Event: {oldest_event['tx_hash'][:10]}...")
                print(f"   Triggering reelection...")
                
                # Broadcast leader failure to all nodes
                failed_leader = self.current_leader
                self.update_reputation(failed_leader, False)
                
                # Notify all other nodes about leader failure
                for port in [5000, 5001, 5002, 5003, 5004, 5005, 5006]:
                    if port == int(NODE_PORT):
                        continue
                    try:
                        requests.post(
                            f"http://127.0.0.1:{port}/leader_failed",
                            json={"failed_leader": failed_leader},
                            timeout=2
                        )
                    except:
                        pass
                
                return True
        
        return False

node_state = NodeState()

def b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("utf-8"))

def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("utf-8")

def load_state():
    if not os.path.exists(STATE_FILE):
        raise FileNotFoundError(f"{STATE_FILE} not found.")
    
    with open(STATE_FILE, "r") as f:
        data = json.load(f)
    
    master_public_key = PublicKey.from_bytes(b64d(data["master_public_key"]))
    authority_public_key = PublicKey.from_bytes(b64d(data["authority_public_key"]))
    bobs_public_key = PublicKey.from_bytes(b64d(data["bobs_public_key"]))
    threshold = data.get("threshold", 4)
    
    return master_public_key, authority_public_key, bobs_public_key, threshold

class ReencryptRequest(BaseModel):
    cipherText: str
    capsule: str

@app.post("/reencrypt")
def reencryptData(data: ReencryptRequest):
    if CORRUPTED:
        # Corrupt the kfrag by flipping some bits
        corrupted_bytes = bytearray(kfrag.__bytes__())
        corrupted_bytes[0] ^= 0xFF  # Flip bits in the first byte
        kfrag_corrupted = VerifiedKeyFrag.from_verified_bytes(bytes(corrupted_bytes))
        kfrag_to_use = kfrag_corrupted
    else:
        kfrag_to_use = kfrag
    capsule_bytes = base64.b64decode(data.capsule)
    capsule = Capsule.from_bytes(capsule_bytes)
    cfrag = reencrypt(capsule=capsule, kfrag=kfrag_to_use)

    return {
        "cFrag": base64.b64encode(cfrag.__bytes__()).decode()
    }

class UserSubmitVoteRequest(BaseModel):
    encrypted_vote: str
    encrypted_sym_key: str
    capsule: str
    current_state: str  # Current encrypted state from contract

@app.post("/submit_vote")
def submit_vote_via_tee(data: UserSubmitVoteRequest):
    try:
        master_public_key, authority_public_key, bobs_public_key, threshold = load_state()
        
        capsule_b64 = data.capsule
        encrypted_sym_key_b64 = data.encrypted_sym_key
        
        # Collect cfrags from all nodes
        NODE_PORTS = [5000, 5001, 5002, 5003, 5004, 5005, 5006]
        NODE_URL_TEMPLATE = "http://127.0.0.1:{port}/reencrypt"
        
        cfrag_b64_list = []
        
        for port in NODE_PORTS:
            url = NODE_URL_TEMPLATE.format(port=port)
            try:
                resp = requests.post(
                    url,
                    json={
                        "cipherText": encrypted_sym_key_b64,
                        "capsule": capsule_b64,
                    },
                    timeout=5,
                )
                resp.raise_for_status()
            except Exception as e:
                print(f"❌ Failed to reach node {port}: {e}")
                continue
            
            node_data = resp.json()
            cfrag_b64 = node_data.get("cFrag")
            if not cfrag_b64:
                print(f"Node {port} did not return 'cFrag' field.")
                continue
            
            try:
                cfrag_bytes = b64d(cfrag_b64)
            except Exception as e:
                print(f"Node {port} returned invalid base64: {e}")
                continue
            
            # Verify the cfrag
            try:
                suspicious_cfrag = CapsuleFrag.from_bytes(cfrag_bytes)
            except Exception as e:
                print(f"❌ Node {port} returned invalid CapsuleFrag: {e}")
                continue
            
            try:
                capsule_obj = Capsule.from_bytes(b64d(capsule_b64))
                
                verified_cfrag = suspicious_cfrag.verify(
                    capsule=capsule_obj,
                    verifying_pk=authority_public_key,
                    delegating_pk=master_public_key,
                    receiving_pk=bobs_public_key,
                )
                cfrag_b64_list.append(b64e(bytes(verified_cfrag)))
                print(f"Node {port} returned a valid cFrag.")
            except VerificationError as e:
                print(f"Verification failed for node {port}: {e}")
                continue
            except Exception as e:
                print(f"Unexpected error verifying cFrag from {port}: {e}")
                continue
        
        print(f"\nCollected {len(cfrag_b64_list)} valid cFrags (threshold = {threshold}).")
        
        if len(cfrag_b64_list) < threshold:
            return {
                "success": False,
                "error": f"Not enough valid cFrags. Needed {threshold}, got {len(cfrag_b64_list)}."
            }
        
        # Call TEE's /submit endpoint
        TEE_URL = "http://127.0.0.1:8000/submit"
        
        print("\nCalling TEE's /submit endpoint...")
        try:
            resp = requests.post(
                TEE_URL,
                json={
                    "encrypted_vote": data.encrypted_vote,
                    "encrypted_sym_key": encrypted_sym_key_b64,
                    "capsule": capsule_b64,
                    "cfrags": cfrag_b64_list,
                    "current_state": data.current_state,
                },
                timeout=10,
            )
            resp.raise_for_status()
            
            result = resp.json()
            return result
        except Exception as e:
            print(f"\nFailed to call TEE: {e}")
            return {
                "success": False,
                "error": f"Failed to call TEE: {str(e)}"
            }
    except Exception as e:
        print(f"Decryption process failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }

# ============================================
# LEADER ELECTION AND CONSENSUS ENDPOINTS
# ============================================

class ElectionVote(BaseModel):
    voter_id: int
    candidate: int
    election_round: int

class ElectionStart(BaseModel):
    election_round: int
    initiator_id: int

class EventNotification(BaseModel):
    tx_hash: str
    block_number: int
    voter: str
    encrypted_vote: str
    encrypted_sym_key: str
    capsule: str
    amount: int

@app.post("/start_election")
def start_election_endpoint(data: ElectionStart):
    """Receive election start notification"""
    if data.election_round >= node_state.election_round:
        print(f"📢 Election {data.election_round} started by Node {data.initiator_id}")
        node_state.election_round = data.election_round
        node_state.election_in_progress = True
        node_state.current_votes = {}
        
        # Cast our vote
        my_candidate = node_state.propose_leader_candidate()
        node_state.cast_vote(NODE_ID, my_candidate)
        
        # Broadcast our vote
        broadcast_vote(my_candidate, data.election_round)
        
        return {"status": "voting"}
    return {"status": "old_round"}

@app.post("/cast_vote")
def receive_vote(data: ElectionVote, background_tasks: BackgroundTasks):
    """Receive a vote from another node"""
    if data.election_round < node_state.election_round:
        return {"status": "old_round"}
    
    # If we get a vote for a round we haven't started, start it
    if data.election_round > node_state.election_round:
        print(f"📢 Received vote for future round {data.election_round}, catching up...")
        node_state.election_round = data.election_round
        node_state.election_in_progress = True
        node_state.current_votes = {}
        
        # Cast our own vote
        my_candidate = node_state.propose_leader_candidate()
        node_state.cast_vote(NODE_ID, my_candidate)
        broadcast_vote(my_candidate, data.election_round)
    
    # Record the vote
    node_state.cast_vote(data.voter_id, data.candidate)
    
    # Check if we have a winner
    winner = node_state.tally_votes()
    if winner is not None:
        return {"status": "election_complete", "leader": winner}
    elif winner is None and len(node_state.current_votes) == 0:
        # Tally returned None and cleared votes = tie detected
        # Only Node 0 triggers re-election to avoid chaos
        if NODE_ID == 0:
            print(f"🔄 Node 0 will trigger re-election due to tie...")
            background_tasks.add_task(delayed_reelection)
        return {"status": "tie_reelection_needed"}
    
    return {"status": "vote_recorded"}

@app.post("/leader_failed")
def leader_failed(data: dict):
    """Receive notification that a leader failed to process"""
    failed_leader = data.get('failed_leader')
    if failed_leader is not None:
        print(f"📉 Received notification: Node {failed_leader} failed to process event")
        node_state.update_reputation(failed_leader, False)
    return {"status": "updated"}

@app.post("/sync_state")
def sync_state(data: dict):
    """Sync processed events and reputation with other nodes"""
    # Merge processed events
    for tx_hash in data.get('processed_events', []):
        node_state.processed_events.add(tx_hash)
    
    # Merge reputation (take max successes/failures)
    for node_id_str, rep_data in data.get('reputation', {}).items():
        node_id = int(node_id_str)
        if node_id in node_state.node_reputation:
            current = node_state.node_reputation[node_id]
            current['successes'] = max(current['successes'], rep_data.get('successes', 0))
            current['failures'] = max(current['failures'], rep_data.get('failures', 0))
            # Recalculate weight
            total = current['successes'] + current['failures']
            if total > 0:
                success_rate = current['successes'] / total
                if success_rate > 0.8:
                    current['weight'] = min(3.0, current['weight'] + 0.1)
                elif success_rate < 0.3:
                    current['weight'] = max(0.1, current['weight'] - 0.2)
    
    return {"synced": True}

@app.get("/get_state")
def get_state():
    """Get current node state for syncing"""
    return {
        "node_id": NODE_ID,
        "current_leader": node_state.current_leader,
        "election_round": node_state.election_round,
        "processed_events": list(node_state.processed_events),
        "reputation": {
            str(k): v for k, v in node_state.node_reputation.items()
        },
        "pending_events_count": len(node_state.pending_events)
    }

@app.post("/notify_event")
def notify_event(data: EventNotification, background_tasks: BackgroundTasks):
    """Receive notification of a new blockchain event"""
    tx_hash = data.tx_hash
    
    if tx_hash in node_state.processed_events:
        return {"status": "already_processed"}
    
    # Add to pending if not already there
    if not any(e['tx_hash'] == tx_hash for e in node_state.pending_events):
        node_state.pending_events.append({
            'tx_hash': tx_hash,
            'block_number': data.block_number,
            'voter': data.voter,
            'encrypted_vote': data.encrypted_vote,
            'encrypted_sym_key': data.encrypted_sym_key,
            'capsule': data.capsule,
            'amount': data.amount,
            'detected_at': time.time()
        })
        print(f"📋 Added event {tx_hash[:10]}... to pending queue ({len(node_state.pending_events)} pending)")
        
        # If no leader elected yet, trigger election
        if node_state.current_leader is None and not node_state.election_in_progress:
            print(f"⚠️  No leader! Node {NODE_ID} triggering election...")
            background_tasks.add_task(trigger_election)
    
    return {"status": "added_to_queue"}

@app.post("/process_as_leader")
def process_as_leader(background_tasks: BackgroundTasks):
    """Leader processes pending events"""
    if not node_state.pending_events:
        return {"status": "no_pending_events"}
    
    if node_state.current_leader != NODE_ID:
        return {"status": "not_leader"}
    
    event = node_state.pending_events[0]
    tx_hash = event['tx_hash']
    wait_time = time.time() - event['detected_at']
    
    print(f"\n{'='*60}")
    print(f"🎯 LEADER (Node {NODE_ID}) processing event {tx_hash[:10]}...")
    print(f"   Event waited: {wait_time:.1f}s")
    print(f"{'='*60}")
    
    try:
        # Load contract to get current state
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        with open(CONTRACT_ADDRESS_FILE, 'r') as f:
            contract_address = json.load(f)['address']
        with open(CONTRACT_ABI_FILE, 'r') as f:
            contract_abi = json.load(f)
        
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=contract_abi
        )
        
        current_state = contract.functions.getCurrentState().call()
        
        # Process the vote
        result = submit_vote_via_tee(UserSubmitVoteRequest(
            encrypted_vote=event['encrypted_vote'],
            encrypted_sym_key=event['encrypted_sym_key'],
            capsule=event['capsule'],
            current_state=current_state
        ))
        
        if result.get('success'):
            # Update contract
            new_state = result.get('new_encrypted_state')
            accounts = w3.eth.accounts
            if accounts:
                tx_hash_update = contract.functions.updateState(new_state).transact({
                    'from': accounts[0],
                    'gas': 3000000
                })
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash_update)
                print(f"✅ State updated in contract (tx: {receipt.transactionHash.hex()[:10]}...)")
            
            # Mark as processed
            node_state.processed_events.add(tx_hash)
            node_state.pending_events.pop(0)
            node_state.update_reputation(NODE_ID, True)
            
            # Notify other nodes
            background_tasks.add_task(broadcast_processed_event, tx_hash, True)
            
            return {"status": "success", "result": result}
        else:
            print(f"❌ Failed to process: {result.get('error')}")
            node_state.update_reputation(NODE_ID, False)
            background_tasks.add_task(broadcast_processed_event, tx_hash, False)
            return {"status": "failed", "error": result.get('error')}
            
    except Exception as e:
        print(f"❌ Error processing event: {e}")
        node_state.update_reputation(NODE_ID, False)
        background_tasks.add_task(broadcast_processed_event, tx_hash, False)
        return {"status": "error", "error": str(e)}

def broadcast_processed_event(tx_hash: str, success: bool):
    """Notify other nodes that event was processed"""
    NODE_PORTS = [5000, 5001, 5002, 5003, 5004, 5005, 5006]
    for port in NODE_PORTS:
        if port == int(NODE_PORT):
            continue
        try:
            requests.post(
                f"http://127.0.0.1:{port}/mark_processed",
                json={"tx_hash": tx_hash, "processed_by": NODE_ID, "success": success},
                timeout=2
            )
        except:
            pass
    
    # After broadcasting, clear current leader to force re-election
    if success:
        node_state.current_leader = None
        print(f"\n🔄 Leader term ended after processing event")
        print(f"   Next election will choose new leader")

@app.post("/mark_processed")
def mark_processed(data: dict, background_tasks: BackgroundTasks):
    """Mark an event as processed by another node"""
    tx_hash = data['tx_hash']
    processed_by = data['processed_by']
    success = data['success']
    
    node_state.processed_events.add(tx_hash)
    node_state.pending_events = [e for e in node_state.pending_events if e['tx_hash'] != tx_hash]
    node_state.update_reputation(processed_by, success)
    
    # After successful processing, clear leader
    if success:
        print(f"✅ Event processed successfully by Node {processed_by}")
        node_state.current_leader = None  # Clear current leader
        
        # Only Node 0 triggers new election to avoid chaos
        if NODE_ID == 0 and node_state.pending_events:
            print(f"🔄 Node 0 will trigger new election for next event...")
            background_tasks.add_task(delayed_reelection)
    
    return {"status": "marked"}

# ============================================
# BLOCKCHAIN MONITORING
# ============================================

def monitor_blockchain():
    """Monitor blockchain for new events and coordinate processing"""
    print(f"\n🔍 Node {NODE_ID} starting blockchain monitoring...")
    
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    time.sleep(2)  # Wait for services to be ready
    
    try:
        with open(CONTRACT_ADDRESS_FILE, 'r') as f:
            contract_address = json.load(f)['address']
        with open(CONTRACT_ABI_FILE, 'r') as f:
            contract_abi = json.load(f)
        
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=contract_abi
        )
    except Exception as e:
        print(f"❌ Failed to load contract: {e}")
        return
    
    last_block = w3.eth.block_number
    print(f"📡 Monitoring from block {last_block}")
    
    # Wait for all nodes to be ready
    time.sleep(5)
    
    # Initial election - only node 0 triggers it
    if NODE_ID == 0:
        print(f"\n🗳️  Node {NODE_ID} initiating first election...")
        trigger_election()
        print(f"✅ Initial election triggered. Waiting for votes...")
        time.sleep(3)
        
        if node_state.current_leader is not None:
            print(f"✅ Leader elected: Node {node_state.current_leader}")
        else:
            print(f"⚠️  No leader elected yet. Votes: {len(node_state.current_votes)}/7")
            print(f"   Current votes: {node_state.current_votes}")
    else:
        print(f"🔍 Node {NODE_ID} waiting for election to be triggered...")
    
    while True:
        try:
            current_block = w3.eth.block_number
            
            # Check for new events
            if current_block > last_block:
                try:
                    event_filter = contract.events.VoteSubmitted.create_filter(
                        from_block=last_block + 1,
                        to_block=current_block
                    )
                    events = event_filter.get_all_entries()
                    
                    for event in events:
                        tx_hash = event['transactionHash'].hex()
                        if tx_hash not in node_state.processed_events:
                            # Broadcast event to all nodes
                            broadcast_new_event(event)
                            
                except Exception as e:
                    print(f"Error fetching events: {e}")
                
                last_block = current_block
            
            # Only Node 0 triggers elections to avoid coordination chaos
            if NODE_ID == 0:
                # If there are pending events and no leader, trigger election
                if node_state.pending_events and node_state.current_leader is None and not node_state.election_in_progress:
                    print(f"\n🗳️  Node {NODE_ID}: Pending events but no leader - triggering election...")
                    trigger_election()
                    time.sleep(2)  # Wait for election to complete
                
                # Check if current leader failed to process (timeout)
                if node_state.should_reelect() and not node_state.election_in_progress:
                    print(f"\n⚠️  Node {NODE_ID} triggering reelection due to leader failure...")
                    trigger_election()
                    time.sleep(2)  # Wait for election to complete
            
            # If I'm the leader and have pending events, process them
            if node_state.current_leader == NODE_ID and node_state.pending_events:
                # Corrupt nodes refuse to process events
                if node_state.is_corrupt:
                    print(f"\n💀 CORRUPT Node {NODE_ID} refuses to process event!")
                    print(f"   (Other nodes will timeout and trigger re-election)")
                    time.sleep(2)  # Just wait, do nothing
                else:
                    # Cooldown to avoid rapid processing
                    time_since_last = time.time() - node_state.last_processed_time
                    if time_since_last > node_state.processing_cooldown:
                        try:
                            print(f"\n⏳ Leader processing event (waited {time_since_last:.1f}s)...")
                            requests.post(f"http://127.0.0.1:{NODE_PORT}/process_as_leader", timeout=60)
                            node_state.last_processed_time = time.time()
                        except Exception as e:
                            print(f"Error processing as leader: {e}")
            
            time.sleep(2)
            
        except Exception as e:
            print(f"Monitor error: {e}")
            time.sleep(5)

def broadcast_new_event(event):
    """Notify all nodes about a new event"""
    NODE_PORTS = [5000, 5001, 5002, 5003, 5004, 5005, 5006]
    event_data = {
        "tx_hash": event['transactionHash'].hex(),
        "block_number": event['blockNumber'],
        "voter": event['args']['voter'],
        "encrypted_vote": event['args']['encryptedVote'],
        "encrypted_sym_key": event['args']['encryptedSymKey'],
        "capsule": event['args']['capsule'],
        "amount": event['args']['amount']
    }
    
    for port in NODE_PORTS:
        try:
            requests.post(
                f"http://127.0.0.1:{port}/notify_event",
                json=event_data,
                timeout=2
            )
        except:
            pass

def delayed_reelection():
    """Trigger re-election after a small delay (for tie-breaking)"""
    time.sleep(1)  # Wait to avoid flooding
    trigger_election()

def trigger_election():
    """Trigger a new election and broadcast to all nodes"""
    node_state.start_election()
    
    # Cast our own vote first
    my_candidate = node_state.propose_leader_candidate()
    node_state.cast_vote(NODE_ID, my_candidate)
    
    # Broadcast election start to all nodes
    NODE_PORTS = [5000, 5001, 5002, 5003, 5004, 5005, 5006]
    for port in NODE_PORTS:
        if port == int(NODE_PORT):
            continue
        try:
            requests.post(
                f"http://127.0.0.1:{port}/start_election",
                json={"election_round": node_state.election_round, "initiator_id": NODE_ID},
                timeout=3
            )
        except Exception as e:
            print(f"Failed to notify node on port {port}: {e}")
    
    # Small delay to let other nodes start
    time.sleep(0.5)
    
    # Broadcast our vote to all nodes
    broadcast_vote(my_candidate, node_state.election_round)
    
    # Wait a bit for votes to come in
    time.sleep(1)
    
    # Check if election completed
    if node_state.current_leader:
        print(f"✅ Election complete! Leader: Node {node_state.current_leader}")
    else:
        print(f"⚠️  Election incomplete. Votes so far: {len(node_state.current_votes)}/7")

def broadcast_vote(candidate: int, election_round: int):
    """Broadcast our vote to all nodes"""
    NODE_PORTS = [5000, 5001, 5002, 5003, 5004, 5005, 5006]
    for port in NODE_PORTS:
        if port == int(NODE_PORT):
            continue
        try:
            resp = requests.post(
                f"http://127.0.0.1:{port}/cast_vote",
                json={"voter_id": NODE_ID, "candidate": candidate, "election_round": election_round},
                timeout=3
            )
            resp.raise_for_status()
        except Exception as e:
            print(f"Failed to send vote to port {port}: {e}")

@app.on_event("startup")
def startup_event():
    """Start blockchain monitoring on startup"""
    if not node_state.is_monitoring:
        node_state.is_monitoring = True
        monitor_thread = threading.Thread(target=monitor_blockchain, daemon=True)
        monitor_thread.start()
