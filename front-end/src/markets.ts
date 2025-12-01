import './style.css';
import { ethers } from 'ethers';

const API_BASE = 'http://127.0.0.1:3001/api';

interface Market {
	marketId: number;
	title: string;
	description: string;
	tokenAddress: string;
	status: number;
	bettingFinished: boolean;
	createdAt: number;
	totalVolume: number;
}

// Ethereum types
declare global {
	interface Window {
		ethereum?: any;
	}
}

let isAdmin = false;
let userAddress: string | null = null;
let provider: ethers.BrowserProvider | null = null;
let signer: ethers.Signer | null = null;

// ERC20 ABI for getting token info
const ERC20_ABI = [
	'function symbol() view returns (string)',
	'function name() view returns (string)',
	'function decimals() view returns (uint8)'
];

// Load all markets
async function loadMarkets() {
	try {
		const response = await fetch(`${API_BASE}/markets`);
		const data = await response.json();

		if (data.success && data.markets) {
			displayMarkets(data.markets);
		}
	} catch (error) {
		console.error('Failed to load markets:', error);
		const grid = document.getElementById('markets-grid')!;
		grid.innerHTML = '<div class="error">Failed to load markets. Make sure the backend is running.</div>';
	}
}

// Display markets in grid
function displayMarkets(markets: Market[]) {
	const grid = document.getElementById('markets-grid')!;

	if (markets.length === 0) {
		grid.innerHTML = '<div class="no-markets">No markets available yet. Create one to get started!</div>';
		return;
	}

	grid.innerHTML = '';

	markets.forEach((market) => {
		const card = document.createElement('div');
		card.className = 'market-card';

		const statusText = market.status === 0 ? 'Active' : market.status === 1 ? 'Finished' : 'Completed';
		const statusClass = market.status === 0 ? 'status-active' : market.status === 1 ? 'status-finished' : 'status-completed';

		const createdDate = new Date(market.createdAt * 1000).toLocaleDateString();

		card.innerHTML = `
			<div class="market-header">
				<h3>${market.title}</h3>
				<span class="market-status ${statusClass}">${statusText}</span>
			</div>
			<p class="market-description">${market.description}</p>
			<div class="market-stats">
				<div class="stat">
					<span class="stat-label">Total Volume:</span>
					<span class="stat-value">${market.totalVolume.toFixed(2)} tokens</span>
				</div>
				<div class="stat">
					<span class="stat-label">Token:</span>
					<span class="stat-value">${market.tokenAddress.slice(0, 6)}...${market.tokenAddress.slice(-4)}</span>
				</div>
				<div class="stat">
					<span class="stat-label">Created:</span>
					<span class="stat-value">${createdDate}</span>
				</div>
			</div>
			<button class="btn-primary market-btn" data-market-id="${market.marketId}">
				${market.status === 0 ? 'Vote Now' : 'View Results'}
			</button>
		`;

		grid.appendChild(card);
	});

	// Add click handlers
	document.querySelectorAll('.market-btn').forEach((btn) => {
		btn.addEventListener('click', (e) => {
			const marketId = (e.target as HTMLElement).getAttribute('data-market-id');
			window.location.href = `/index.html?marketId=${marketId}`;
		});
	});
}

// Handle create market form with MetaMask
document.getElementById('create-market-form')!.addEventListener('submit', async (e) => {
	e.preventDefault();

	const title = (document.getElementById('market-title') as HTMLInputElement).value;
	const description = (document.getElementById('market-description') as HTMLTextAreaElement).value;
	const tokenAddress = (document.getElementById('market-token') as HTMLInputElement).value;
	const resultDiv = document.getElementById('create-result')!;
	const button = document.getElementById('create-market-button') as HTMLButtonElement;

	if (!isAdmin || !userAddress) {
		resultDiv.textContent = '✗ Not authorized: Admin only';
		resultDiv.className = 'vote-result error show';
		return;
	}

	if (!signer) {
		resultDiv.textContent = '✗ Please connect MetaMask first';
		resultDiv.className = 'vote-result error show';
		return;
	}

	button.disabled = true;
	resultDiv.textContent = 'Checking network...';
	resultDiv.className = 'vote-result loading show';

	try {
		// Step 0: Check if on BSC Testnet
		const network = await provider!.getNetwork();
		const chainId = Number(network.chainId);
		
		if (chainId !== 97) {
			throw new Error(`Wrong network! Please switch to BSC Testnet (Chain ID: 97). Current: ${chainId}`);
		}

		// Step 1: Get initial state from backend
		resultDiv.textContent = 'Preparing market data...';
		const response = await fetch(`${API_BASE}/markets/create`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
			},
			body: JSON.stringify({ 
				title, 
				description,
				tokenAddress,
				adminAddress: userAddress 
			}),
		});

		const data = await response.json();

		if (!data.success) {
			throw new Error(data.error || 'Failed to prepare market data');
		}

		// Step 2: Load contract ABI
		resultDiv.textContent = 'Loading contract...';
		const contractAbiResponse = await fetch('/contract-abi.json');
		const contractAbi = await contractAbiResponse.json();

		// Step 3: Create contract instance
		const contract = new ethers.Contract(data.contractAddress, contractAbi, signer);

		// Step 4: Send transaction via MetaMask
		resultDiv.textContent = 'Sending transaction to blockchain...';
		const tx = await contract.createMarket(
			title,
			description,
			ethers.getAddress(data.tokenAddress),
			data.initialState,
			ethers.getBytes(data.initialSignature)
		);

		resultDiv.textContent = 'Waiting for confirmation...';
		const receipt = await tx.wait();

		if (receipt.status === 1) {
			// Get market count to determine new market ID
			const marketCount = await contract.marketCount();
			const newMarketId = Number(marketCount) - 1;

			resultDiv.textContent = `✓ Market created successfully! (ID: ${newMarketId})`;
			resultDiv.className = 'vote-result success show';
			
			// Clear form
			(document.getElementById('market-title') as HTMLInputElement).value = '';
			(document.getElementById('market-description') as HTMLTextAreaElement).value = '';
			(document.getElementById('market-token') as HTMLInputElement).value = '';

			// Reload markets
			setTimeout(() => {
				loadMarkets();
				resultDiv.textContent = '';
				resultDiv.className = 'vote-result';
			}, 2000);
		} else {
			throw new Error('Transaction failed');
		}
	} catch (error: any) {
		console.error('Create market error:', error);
		resultDiv.className = 'vote-result error show';
		
		// Clean error message handling
		let errorMessage = 'Failed to create market';
		
		if (error.code === 'ACTION_REJECTED' || error.code === 4001) {
			errorMessage = 'Transaction cancelled by user';
		} else if (error.message) {
			if (error.message.includes('user rejected')) {
				errorMessage = 'Transaction cancelled by user';
			} else if (error.message.includes('insufficient funds')) {
				errorMessage = 'Insufficient funds for gas';
			} else if (error.message.includes('Wrong network')) {
				errorMessage = error.message;
			} else if (error.message.includes('Not authorized')) {
				errorMessage = 'Not authorized: Admin only';
			} else if (error.reason) {
				errorMessage = error.reason;
			} else if (error.message.length < 100) {
				errorMessage = error.message;
			} else {
				errorMessage = 'Failed to create market. Check console for details';
			}
		}
		
		resultDiv.textContent = `✗ ${errorMessage}`;
	} finally {
		button.disabled = false;
	}
});

// Update wallet button display
function updateWalletButton(address: string) {
	const connectBtn = document.getElementById('wallet-connect-btn') as HTMLButtonElement;
	
	connectBtn.innerHTML = `
		<span class="wallet-icon">🦊</span>
		<span class="wallet-text">${address.slice(0, 6)}...${address.slice(-4)}</span>
	`;
	
	connectBtn.classList.add('connected');
}

// Connect wallet
async function connectWallet() {
	try {
		if (!window.ethereum) {
			alert('Please install MetaMask!');
			return;
		}

		provider = new ethers.BrowserProvider(window.ethereum);
		
		// Check network
		const network = await provider.getNetwork();
		const chainId = Number(network.chainId);
		
		if (chainId !== 97) {
			alert(`Wrong network! Please switch MetaMask to BSC Testnet (Chain ID: 97).\n\nCurrent network: ${chainId}`);
			return;
		}

		const accounts = await provider.send('eth_requestAccounts', []);
		userAddress = accounts[0];
		signer = await provider.getSigner();

		// Update button
		updateWalletButton(userAddress);

		// Check if user is admin
		await checkAdminStatus();
	} catch (error: any) {
		console.error('Failed to connect wallet:', error);
		
		let errorMessage = 'Failed to connect wallet';
		
		if (error.code === 'ACTION_REJECTED' || error.code === 4001) {
			errorMessage = 'Connection cancelled by user';
		} else if (error.message?.includes('user rejected')) {
			errorMessage = 'Connection cancelled by user';
		} else if (error.message?.includes('Wrong network')) {
			return;
		} else if (error.message && error.message.length < 80) {
			errorMessage = error.message;
		}
		
		alert(errorMessage);
	}
}

// Disconnect wallet
function disconnectWallet() {
	userAddress = null;
	signer = null;
	provider = null;
	isAdmin = false;

	const connectBtn = document.getElementById('wallet-connect-btn') as HTMLButtonElement;
	const createSection = document.getElementById('create-market-section')!;

	connectBtn.innerHTML = `
		<span class="wallet-icon">🦊</span>
		<span class="wallet-text">Connect Wallet</span>
	`;
	connectBtn.classList.remove('connected');
	createSection.style.display = 'none';
}

// Check if connected user is admin
async function checkAdminStatus() {
	if (!userAddress) return;
	
	try {
		const response = await fetch(`${API_BASE}/admin/verify`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ address: userAddress })
		});
		
		const data = await response.json();
		isAdmin = data.success && data.isAdmin;
		
		// Show/hide create market section
		const createSection = document.getElementById('create-market-section')!;
		createSection.style.display = isAdmin ? 'block' : 'none';
	} catch (error) {
		console.error('Failed to check admin status:', error);
		isAdmin = false;
	}
}

// Try to auto-reconnect if wallet was previously connected
if (window.ethereum) {
	window.ethereum.request({ method: 'eth_accounts' })
		.then((accounts: string[]) => {
			if (accounts.length > 0) {
				connectWallet();
			}
		})
		.catch((error: any) => {
			console.log('Auto-reconnect not available');
		});
}

// Setup wallet connection button
const walletBtn = document.getElementById('wallet-connect-btn') as HTMLButtonElement;
walletBtn.addEventListener('click', async () => {
	if (userAddress) {
		if (confirm('Disconnect wallet?')) {
			disconnectWallet();
		}
	} else {
		await connectWallet();
	}
});

// Listen for account changes
if (window.ethereum) {
	window.ethereum.on('accountsChanged', (accounts: string[]) => {
		if (accounts.length === 0) {
			disconnectWallet();
		} else {
			connectWallet();
		}
	});
	
	// Listen for network changes
	window.ethereum.on('chainChanged', () => {
		window.location.reload();
	});
}

// Token address validation and symbol fetching
const tokenInput = document.getElementById('market-token') as HTMLInputElement;
const tokenSymbolDisplay = document.getElementById('token-symbol-display') as HTMLDivElement;
let tokenValidationTimeout: any = null;

tokenInput.addEventListener('input', () => {
	clearTimeout(tokenValidationTimeout);
	tokenSymbolDisplay.textContent = '';
	
	const address = tokenInput.value.trim();
	
	if (!address || !ethers.isAddress(address)) {
		return;
	}
	
	tokenValidationTimeout = setTimeout(async () => {
		try {
			if (!provider) {
				tokenSymbolDisplay.textContent = '⚠ Connect wallet to verify token';
				tokenSymbolDisplay.style.color = '#ffa500';
				return;
			}
			
			const tokenContract = new ethers.Contract(address, ERC20_ABI, provider);
			const symbol = await tokenContract.symbol();
			const name = await tokenContract.name();
			
			tokenSymbolDisplay.textContent = `✓ Token: ${name} (${symbol})`;
			tokenSymbolDisplay.style.color = '#00ff88';
		} catch (error) {
			tokenSymbolDisplay.textContent = '✗ Invalid token address';
			tokenSymbolDisplay.style.color = '#ff4444';
		}
	}, 800);
});

// Initial load
loadMarkets();

// Refresh markets every 10 seconds
setInterval(loadMarkets, 10000);
