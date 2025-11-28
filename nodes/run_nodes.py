import json
import os
import subprocess
from typing import List
import random

STATE_FILE = "../kd/umbral_state.json"
BASE_PORT = int(os.getenv("BASE_PORT", "5000"))
NUM_NODES_ENV = os.getenv("NUM_NODES", 7)


def load_kfrags_from_state(state_file: str) -> List[str]:
    with open(state_file, "r") as f:
        data = json.load(f)
    kfrags = data.get("kfrags", [])
    if not kfrags:
        raise RuntimeError("No kfrags found in state file.")
    return kfrags


def main():
    if not os.path.exists(STATE_FILE):
        raise FileNotFoundError(
            f"{STATE_FILE} not found. Generate it first with your key-generation script."
        )

    kfrags = load_kfrags_from_state(STATE_FILE)

    if NUM_NODES_ENV is not None:
        num_nodes = min(int(NUM_NODES_ENV), len(kfrags))
    else:
        num_nodes = len(kfrags)

    print(f"Starting {num_nodes} nodes from {len(kfrags)} available kfrags...")
    processes = []

    corrupt_indexes = random.sample(range(num_nodes), 2)

    for idx in range(num_nodes):
        port = BASE_PORT + idx
        kfrag_b64 = kfrags[idx]

        env = os.environ.copy()
        env["KFRAG"] = kfrag_b64
        env["NODE_PORT"] = str(port)
        if idx in corrupt_indexes:
            env["CORRUPTED"] = "1"

        cmd = [
            "uvicorn",
            "node:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
        ]

        print(f"Starting node {idx} on port {port} with its own KFRAG...")
        p = subprocess.Popen(cmd, env=env)
        processes.append(p)

    print("All nodes started. PIDs:", [p.pid for p in processes])
    print("Press Ctrl+C to stop them (or kill the PIDs manually).")

    try:
        for p in processes:
            p.wait()
    except KeyboardInterrupt:
        print("\nStopping all nodes...")
        for p in processes:
            p.terminate()


if __name__ == "__main__":
    main()
