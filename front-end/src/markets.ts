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
let adminAddress = '';
let provider: ethers.BrowserProvider | null = null;
let signer: ethers.Signer | null = null;

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

	if (!isAdmin || !adminAddress) {
		resultDiv.textContent = '✗ Not authorized: Please login as admin';
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
				adminAddress 
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

// Check admin status on load
async function checkAdminStatus() {
	try {
		const response = await fetch(`${API_BASE}/admin/status`);
		const data = await response.json();

		if (data.success && data.adminAddress) {
			// Check if logged in as admin (from localStorage)
			const savedAdmin = localStorage.getItem('adminAddress');
			if (savedAdmin && savedAdmin.toLowerCase() === data.adminAddress.toLowerCase()) {
				isAdmin = true;
				adminAddress = savedAdmin;
				updateUIForAdmin();
			}
		}
	} catch (error) {
		console.error('Failed to check admin status:', error);
	}
}

function updateUIForAdmin() {
	const loginBtn = document.getElementById('admin-login-btn')!;
	const createSection = document.getElementById('create-market-section')!;

	if (isAdmin) {
		loginBtn.textContent = `Admin: ${adminAddress.slice(0, 6)}...${adminAddress.slice(-4)}`;
		loginBtn.className = 'btn-success';
		createSection.style.display = 'block';

		// Add logout functionality
		loginBtn.onclick = () => {
			if (confirm('Logout from admin?')) {
				localStorage.removeItem('adminAddress');
				isAdmin = false;
				adminAddress = '';
				loginBtn.textContent = 'Admin Login';
				loginBtn.className = 'btn-secondary';
				createSection.style.display = 'none';
				loginBtn.onclick = showLoginModal;
			}
		};
	} else {
		loginBtn.textContent = 'Admin Login';
		loginBtn.className = 'btn-secondary';
		createSection.style.display = 'none';
		loginBtn.onclick = showLoginModal;
	}
}

// Connect MetaMask for admin
async function connectMetaMaskAdmin() {
	const resultDiv = document.getElementById('login-result')!;
	
	try {
		if (!window.ethereum) {
			alert('Please install MetaMask to login as admin!');
			return;
		}

		resultDiv.textContent = 'Connecting to MetaMask...';
		resultDiv.className = 'vote-result loading show';

		// Request account access
		provider = new ethers.BrowserProvider(window.ethereum);
		const accounts = await provider.send('eth_requestAccounts', []);
		const address = accounts[0];
		signer = await provider.getSigner();

		resultDiv.textContent = 'Verifying admin status...';

		// Verify if this address is the admin
		const response = await fetch(`${API_BASE}/admin/verify`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
			},
			body: JSON.stringify({ address }),
		});

		const data = await response.json();

		if (data.success && data.isAdmin) {
			resultDiv.textContent = '✓ Admin verified!';
			resultDiv.className = 'vote-result success show';
			
			// Save to localStorage
			localStorage.setItem('adminAddress', address);
			isAdmin = true;
			adminAddress = address;

			setTimeout(() => {
				const modal = document.getElementById('admin-login-modal')!;
				modal.classList.remove('show');
				updateUIForAdmin();
				resultDiv.textContent = '';
			}, 1000);
		} else {
			resultDiv.textContent = '✗ Not an admin address';
			resultDiv.className = 'vote-result error show';
		}
	} catch (error: any) {
		console.error('Admin login error:', error);
		resultDiv.className = 'vote-result error show';
		
		// Clean error message handling
		let errorMessage = 'Failed to connect';
		
		if (error.code === 'ACTION_REJECTED' || error.code === 4001) {
			errorMessage = 'Connection cancelled by user';
		} else if (error.message) {
			if (error.message.includes('user rejected')) {
				errorMessage = 'Connection cancelled by user';
			} else if (error.message.length < 80) {
				errorMessage = error.message;
			} else {
				errorMessage = 'Connection failed. Check console for details';
			}
		}
		
		resultDiv.textContent = `✗ ${errorMessage}`;
	}
}

// Admin login modal
function showLoginModal() {
	const modal = document.getElementById('admin-login-modal')!;
	const resultDiv = document.getElementById('login-result')!;
	resultDiv.textContent = '';
	resultDiv.className = 'vote-result';
	modal.classList.add('show');
}

document.getElementById('cancel-login')!.addEventListener('click', () => {
	const modal = document.getElementById('admin-login-modal')!;
	const resultDiv = document.getElementById('login-result')!;
	resultDiv.textContent = '';
	resultDiv.className = 'vote-result';
	modal.classList.remove('show');
});

// MetaMask login button - the only way to login
document.getElementById('metamask-login')!.addEventListener('click', async () => {
	await connectMetaMaskAdmin();
});

// Set initial click handler for admin button
document.getElementById('admin-login-btn')!.onclick = showLoginModal;

// Initial load
checkAdminStatus();
loadMarkets();

// Refresh markets every 10 seconds
setInterval(loadMarkets, 10000);
