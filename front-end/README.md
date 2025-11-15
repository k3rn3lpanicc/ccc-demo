# Private Market Prediction - Frontend

A dark forest themed frontend (black and green + blue) for the private market prediction system built with Vite and vanilla TypeScript.

## Features

- 📊 **Real-time A-Ratio Chart**: Displays the ratio of votes for option A over time
- 🗳️ **Vote Submission**: Cast votes using predefined Hardhat accounts
- 🔒 **Privacy Aware**: Shows when a_ratio is revealed (every 5 votes) vs hidden
- ⚡ **Live Updates**: Auto-refreshes data every 5 seconds
- 🎨 **Dark Forest Theme**: Black background with green and blue accents

## Prerequisites

Before running the frontend, make sure the following are running:

1. **Hardhat Node**: `npm run node` (in project root)
2. **TEE Service**: `python -m uvicorn tee:app` (in project root)
3. **Threshold Nodes**: `python run_nodes.py` (in nodes directory)
4. **Contract Listener**: `python contract_listener.py` (in project root)
5. **Frontend API**: `python frontend_api.py` (in project root)

## Installation

```bash
cd front-end
npm install
```

## Running the Frontend

```bash
npm run dev
```

The frontend will be available at `http://localhost:3000`

## Usage

1. **View Contract Status**: See the contract address, balance, and betting status
2. **Monitor A-Ratio**: Watch the chart update as votes come in (every 5 votes)
3. **Submit Votes**:
   - Select a Hardhat account (1-8)
   - Enter bet amount in ETH
   - Choose option A or B
   - Click "Submit Vote"
4. **Wait for Processing**: The listener will process the vote and update the chart

## Architecture

```
Frontend (Port 3000)
    ↓
Frontend API (Port 3001)
    ↓
Web3 → Smart Contract → Contract Listener → Nodes → TEE
```

## API Endpoints

The frontend communicates with the backend API (`frontend_api.py`) on port 3001:

- `GET /api/history` - Get a_ratio history
- `GET /api/accounts` - Get available Hardhat accounts
- `GET /api/contract/status` - Get contract status
- `POST /api/vote` - Submit a vote

## Privacy Feature

The a_ratio is only revealed when `total_votes % 5 == 0` to prevent identification of individual voters. The chart will only show data points at these intervals.

## Theme

The UI uses a "dark forest" theme:
- **Background**: Pure black with subtle green scan lines
- **Primary Color**: Bright green (#00ff41)
- **Secondary Color**: Blue (#00a8ff)
- **Font**: Courier New (monospace)
- **Style**: Terminal/hacker aesthetic with glowing effects

## Building for Production

```bash
npm run build
```

The built files will be in the `dist` directory.

## Notes

- The frontend uses Chart.js for the time-series visualization
- All accounts are from Hardhat's predefined test accounts
- No wallet connection needed - accounts are selected from a dropdown
- The system automatically encrypts votes using Umbral threshold encryption
