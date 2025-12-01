import './style.css';
import { Chart, registerables } from 'chart.js';
import { ethers } from 'ethers';

Chart.register(...registerables);

const API_BASE = 'http://127.0.0.1:3001/api';

// Get marketId from URL parameter
const urlParams = new URLSearchParams(window.location.search);
const MARKET_ID = parseInt(urlParams.get('marketId') || '0');

interface HistoryEntry {
	timestamp: string;
	a_ratio: number;
	a_funds_ratio: number;
	total_votes: number;
}

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

let chart: Chart | null = null;
let lastHistoryLength = 0;
let currentMarket: Market | null = null;
let provider: ethers.BrowserProvider | null = null;
let signer: ethers.Signer | null = null;
let userAddress: string | null = null;
let userBalance: string = '0';
let isAdmin: boolean = false;

// Load market details
async function loadMarketDetails() {
	try {
		const response = await fetch(`${API_BASE}/markets/${MARKET_ID}`);
		const data = await response.json();

		if (data.success && data.market) {
			currentMarket = data.market;

			// Update page with market info
			document.getElementById('contract-address')!.textContent = `Market #${MARKET_ID}`;
			document.getElementById(
				'contract-balance'
			)!.textContent = `${data.market.totalVolume.toFixed(2)} tokens`;

			// Show token address
			const tokenInfo = document.getElementById('token-info');
			if (tokenInfo) {
				tokenInfo.textContent = `Token: ${data.market.tokenAddress.slice(
					0,
					10
				)}...${data.market.tokenAddress.slice(-8)}`;
			}

			const statusText = data.market.bettingFinished ? '🔴 Finished' : '🟢 Active';
			document.getElementById('betting-status')!.textContent = statusText;

			// Disable voting if finished
			const voteButton = document.getElementById('vote-button') as HTMLButtonElement;
			const finishButton = document.getElementById('finish-button') as HTMLButtonElement;
			if (data.market.bettingFinished) {
				voteButton.disabled = true;
				voteButton.textContent = 'Betting Closed';
				finishButton.disabled = true;
			}
		}
	} catch (error) {
		console.error('Failed to load market:', error);
		document.getElementById('contract-address')!.textContent = 'Error loading';
		document.getElementById('contract-balance')!.textContent = 'Error loading';
		document.getElementById('betting-status')!.textContent = 'Error loading';
	}
}

// Connect to MetaMask
async function connectWallet() {
	const connectBtn = document.getElementById('wallet-connect-btn') as HTMLButtonElement;
	const voteForm = document.getElementById('vote-form') as HTMLFormElement;

	try {
		if (!window.ethereum) {
			alert('Please install MetaMask to use this app!');
			return;
		}

		// Request account access
		provider = new ethers.BrowserProvider(window.ethereum);

		// Check network first
		const network = await provider.getNetwork();
		const chainId = Number(network.chainId);

		if (chainId !== 97) {
			alert(
				`Wrong network! Please switch MetaMask to BSC Testnet (Chain ID: 97).\n\nCurrent network: ${chainId}`
			);
			return;
		}

		const accounts = await provider.send('eth_requestAccounts', []);
		userAddress = accounts[0];
		signer = await provider.getSigner();

		// Update button to show connected state
		updateWalletButton(userAddress!, null, null);
		enableVoteForm();

		// Check if we have a market and token address
		if (
			!currentMarket ||
			!currentMarket.tokenAddress ||
			currentMarket.tokenAddress === '0x0000000000000000000000000000000000000000'
		) {
			// No token yet, just show connected
			await checkAdminStatus();
			return;
		}

		// Get token balance
		try {
			const tokenAbiResponse = await fetch('/token-abi.json');
			const tokenAbi = await tokenAbiResponse.json();

			const tokenContract = new ethers.Contract(
				currentMarket.tokenAddress,
				tokenAbi,
				provider
			);

			const balance = await tokenContract.balanceOf(userAddress);
			const symbol = await tokenContract.symbol();
			userBalance = ethers.formatEther(balance);

			// Update button with balance
			updateWalletButton(userAddress!, parseFloat(userBalance).toFixed(2), symbol);
			enableVoteForm();

			// Check if user is admin
			await checkAdminStatus();
		} catch (tokenError) {
			console.error('Token error:', tokenError);
			// Still show connected even if token check fails
			updateWalletButton(userAddress!, null, null);
			enableVoteForm();

			// Check if user is admin
			await checkAdminStatus();
		}
	} catch (error: any) {
		console.error('Failed to connect wallet:', error);

		// Clean error message handling
		let errorMessage = 'Failed to connect wallet';

		if (error.code === 'ACTION_REJECTED' || error.code === 4001) {
			errorMessage = 'Connection cancelled by user';
		} else if (error.message) {
			if (error.message.includes('user rejected')) {
				errorMessage = 'Connection cancelled by user';
			} else if (error.message.includes('Wrong network')) {
				// Don't show alert, already shown in function
				return;
			} else if (error.message.length < 80) {
				errorMessage = error.message;
			} else {
				errorMessage = 'Connection failed. Please try again';
			}
		}

		alert(errorMessage);
	}
}

// Update wallet button display
function updateWalletButton(address: string, balance: string | null, symbol: string | null) {
	const connectBtn = document.getElementById('wallet-connect-btn') as HTMLButtonElement;

	if (balance && symbol) {
		// Show address and balance
		connectBtn.innerHTML = `
			<span class="wallet-icon">🦊</span>
			<div class="wallet-info">
				<div class="wallet-address">${address.slice(0, 6)}...${address.slice(-4)}</div>
				<div class="wallet-balance">${balance} ${symbol}</div>
			</div>
		`;
	} else {
		// Show just address
		connectBtn.innerHTML = `
			<span class="wallet-icon">🦊</span>
			<span class="wallet-text">${address.slice(0, 6)}...${address.slice(-4)}</span>
		`;
	}

	connectBtn.classList.add('connected');
}

// Enable vote form when wallet connected
function enableVoteForm() {
	const walletPrompt = document.getElementById('wallet-connect-prompt')!;
	const betAmount = document.getElementById('bet-amount') as HTMLInputElement;
	const voteButton = document.getElementById('vote-button') as HTMLButtonElement;
	const radioOptions = document.querySelectorAll('input[name="vote-option"]');

	walletPrompt.style.display = 'none';
	betAmount.disabled = false;
	voteButton.disabled = false;
	voteButton.textContent = 'Submit Vote';
	radioOptions.forEach((radio: any) => (radio.disabled = false));
}

// Disable vote form when wallet disconnected
function disableVoteForm() {
	const walletPrompt = document.getElementById('wallet-connect-prompt')!;
	const betAmount = document.getElementById('bet-amount') as HTMLInputElement;
	const voteButton = document.getElementById('vote-button') as HTMLButtonElement;
	const radioOptions = document.querySelectorAll('input[name="vote-option"]');

	walletPrompt.style.display = 'block';
	betAmount.disabled = true;
	voteButton.disabled = true;
	voteButton.textContent = 'Connect Wallet to Vote';
	radioOptions.forEach((radio: any) => (radio.disabled = true));
}

// Disconnect wallet
function disconnectWallet() {
	userAddress = null;
	signer = null;
	provider = null;
	userBalance = '0';

	const connectBtn = document.getElementById('wallet-connect-btn') as HTMLButtonElement;

	connectBtn.innerHTML = `
		<span class="wallet-icon">🦊</span>
		<span class="wallet-text">Connect Wallet</span>
	`;
	connectBtn.classList.remove('connected');
	disableVoteForm();
	isAdmin = false;
	updateFinishButtonVisibility();
}

// Check if connected user is admin
async function checkAdminStatus() {
	if (!userAddress) return;

	try {
		const response = await fetch(`${API_BASE}/admin/verify`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ address: userAddress }),
		});

		const data = await response.json();
		isAdmin = data.success && data.isAdmin;
		updateFinishButtonVisibility();
	} catch (error) {
		console.error('Failed to check admin status:', error);
		isAdmin = false;
		updateFinishButtonVisibility();
	}
}

// Update finish button visibility based on admin status
function updateFinishButtonVisibility() {
	const finishButton = document.getElementById('finish-button');
	if (finishButton) {
		finishButton.style.display = isAdmin ? 'inline-block' : 'none';
	}
}

// Load and display chart
async function loadChart() {
	try {
		const response = await fetch(`${API_BASE}/history/${MARKET_ID}`);
		const data = await response.json();

		if (data.success && data.history.length > 0) {
			const history: HistoryEntry[] = data.history;

			// Only update if data changed
			if (history.length === lastHistoryLength && chart) {
				return;
			}

			lastHistoryLength = history.length;

			// Hide no-data message
			document.getElementById('no-data-message')!.style.display = 'none';

			// Prepare chart data
			const labels = history.map((entry) => {
				const date = new Date(entry.timestamp);
				return date.toLocaleTimeString();
			});

			const aRatios = history.map((entry) => entry.a_ratio * 100); // Convert to percentage
			const aFundsRatios = history.map((entry) => entry.a_funds_ratio * 100); // Convert to percentage
			const votes = history.map((entry) => entry.total_votes);

			// Create or update chart
			const canvas = document.getElementById('ratioChart') as HTMLCanvasElement;
			const ctx = canvas.getContext('2d')!;

			if (chart) {
				// Update existing chart data instead of destroying
				chart.data.labels = labels;
				chart.data.datasets[0].data = aRatios;
				chart.data.datasets[1].data = aFundsRatios;
				chart.update('none'); // Update without animation
			} else {
				// Create new chart
				chart = new Chart(ctx, {
					type: 'line',
					data: {
						labels: labels,
						datasets: [
							{
								label: 'A-Ratio (% of votes)',
								data: aRatios,
								borderColor: '#00d9ff',
								backgroundColor: 'rgba(0, 217, 255, 0.1)',
								borderWidth: 3,
								fill: true,
								tension: 0.4,
								pointRadius: 6,
								pointBackgroundColor: '#00d9ff',
								pointBorderColor: '#000',
								pointBorderWidth: 2,
								pointHoverRadius: 8,
							},
							{
								label: 'A-Funds-Ratio (% of funds)',
								data: aFundsRatios,
								borderColor: '#00ffcc',
								backgroundColor: 'rgba(0, 255, 204, 0.1)',
								borderWidth: 3,
								fill: true,
								tension: 0.4,
								pointRadius: 6,
								pointBackgroundColor: '#00ffcc',
								pointBorderColor: '#000',
								pointBorderWidth: 2,
								pointHoverRadius: 8,
							},
						],
					},
					options: {
						responsive: true,
						maintainAspectRatio: false,
						animation: {
							duration: 750,
						},
						scales: {
							y: {
								beginAtZero: true,
								max: 100,
								ticks: {
									color: '#8ab4f8',
									callback: function (value) {
										return value + '%';
									},
								},
								grid: {
									color: 'rgba(26, 77, 94, 0.3)',
								},
							},
							x: {
								ticks: {
									color: '#8ab4f8',
									maxRotation: 45,
									minRotation: 45,
								},
								grid: {
									color: 'rgba(26, 77, 94, 0.3)',
								},
							},
						},
						plugins: {
							legend: {
								labels: {
									color: '#00d9ff',
									font: {
										family: "'Courier New', monospace",
										size: 14,
									},
								},
							},
							tooltip: {
								backgroundColor: '#0d1117',
								titleColor: '#00d9ff',
								bodyColor: '#8ab4f8',
								borderColor: '#00d9ff',
								borderWidth: 1,
								callbacks: {
									label: function (context) {
										const index = context.dataIndex;
										const datasetLabel = context.dataset.label;
										return `${datasetLabel}: ${context.parsed.y!.toFixed(2)}%`;
									},
									afterLabel: function (context) {
										const index = context.dataIndex;
										if (context.datasetIndex === 0) {
											return `Total Votes: ${votes[index]}`;
										}
										return '';
									},
								},
							},
						},
					},
				});
			}
		} else {
			// Show no-data message
			document.getElementById('no-data-message')!.style.display = 'block';
		}
	} catch (error) {
		console.error('Failed to load chart data:', error);
	}
}

// Handle vote submission with MetaMask
async function handleVoteSubmit(event: Event) {
	event.preventDefault();

	if (!signer || !userAddress || !currentMarket) {
		alert('Please connect your wallet first!');
		return;
	}

	const betAmount = parseFloat((document.getElementById('bet-amount') as HTMLInputElement).value);
	const betOn = (document.querySelector('input[name="vote-option"]:checked') as HTMLInputElement)
		.value;

	const submitButton = document.getElementById('vote-button') as HTMLButtonElement;
	const resultDiv = document.getElementById('vote-result')!;

	// Show loading state
	submitButton.disabled = true;
	submitButton.textContent = 'Processing...';
	resultDiv.className = 'vote-result loading show';
	resultDiv.textContent = 'Checking network...';

	try {
		// Check if on BSC Testnet
		const network = await provider!.getNetwork();
		const chainId = Number(network.chainId);

		if (chainId !== 97) {
			throw new Error(
				`Wrong network! Please switch MetaMask to BSC Testnet (Chain ID: 97).\n\nCurrent network: ${chainId}`
			);
		}

		resultDiv.textContent = 'Preparing transaction...';

		// Load contract ABIs
		const contractAbiResponse = await fetch('/contract-abi.json');
		const contractAbi = await contractAbiResponse.json();

		const tokenAbiResponse = await fetch('/token-abi.json');
		const tokenAbi = await tokenAbiResponse.json();

		// Get contract address
		const addressResponse = await fetch('/contract-address.json');
		const addressData = await addressResponse.json();
		const contractAddress = addressData.address;

		// Create contract instances
		const contract = new ethers.Contract(contractAddress, contractAbi, signer);
		const token = new ethers.Contract(currentMarket.tokenAddress, tokenAbi, signer);

		const betAmountWei = ethers.parseEther(betAmount.toString());

		// Step 1: Get encrypted vote from backend
		resultDiv.textContent = 'Encrypting vote...';
		const encryptResponse = await fetch(`${API_BASE}/encrypt-vote`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				marketId: MARKET_ID,
				userAddress,
				betAmount: betAmountWei.toString(),
				betOn,
			}),
		});

		const encryptData = await encryptResponse.json();
		if (!encryptData.success) {
			throw new Error(encryptData.error || 'Failed to encrypt vote');
		}

		// Step 2: Approve token
		resultDiv.textContent = 'Approving tokens...';
		const approveTx = await token.approve(contractAddress, betAmountWei);
		await approveTx.wait();

		// Step 3: Submit vote to contract
		resultDiv.textContent = 'Submitting vote to blockchain...';
		const voteTx = await contract.vote(
			MARKET_ID,
			encryptData.encryptedVote,
			encryptData.encryptedSymKey,
			encryptData.capsule,
			betAmountWei
		);

		const receipt = await voteTx.wait();

		resultDiv.className = 'vote-result success show';
		resultDiv.innerHTML = `
			Vote submitted successfully!<br>
			<small>Tx: ${receipt.hash.slice(0, 20)}...</small><br>
			<small>Block: ${receipt.blockNumber}</small><br>
			<small>Waiting for listener to process...</small>
		`;

		// Reload data after a delay
		setTimeout(() => {
			loadMarketDetails();
			loadChart();
			connectWallet(); // Refresh balance
		}, 3000);
	} catch (error: any) {
		console.error('Vote submission error:', error);
		resultDiv.className = 'vote-result error show';

		// Clean error message handling
		let errorMessage = 'Transaction failed';

		if (error.code === 'ACTION_REJECTED' || error.code === 4001) {
			errorMessage = 'Transaction cancelled by user';
		} else if (error.message) {
			// Extract clean error message
			if (error.message.includes('user rejected')) {
				errorMessage = 'Transaction cancelled by user';
			} else if (error.message.includes('insufficient funds')) {
				errorMessage = 'Insufficient funds for gas';
			} else if (error.message.includes('nonce')) {
				errorMessage = 'Transaction nonce error. Please try again';
			} else if (error.message.includes('gas required exceeds allowance')) {
				errorMessage = 'Gas limit too low. Please increase gas limit';
			} else if (error.reason) {
				errorMessage = error.reason;
			} else if (error.message.length < 100) {
				errorMessage = error.message;
			} else {
				// Message too long, show generic error
				errorMessage = 'Transaction failed. Check console for details';
			}
		}

		resultDiv.textContent = `✗ ${errorMessage}`;
	} finally {
		submitButton.disabled = false;
		submitButton.textContent = 'Submit Vote';
	}
}

// Handle finish prediction
async function handleFinishPrediction() {
	if (!signer || !userAddress || !currentMarket) {
		alert('Please connect your wallet first!');
		return;
	}

	const modal = document.getElementById('finish-modal')!;
	const resultDiv = document.getElementById('finish-result')!;
	const confirmButton = document.getElementById('confirm-finish') as HTMLButtonElement;
	const cancelButton = document.getElementById('cancel-finish') as HTMLButtonElement;
	const finishButton = document.getElementById('finish-button') as HTMLButtonElement;

	// Show modal
	modal.classList.add('show');

	// Reset result
	resultDiv.className = 'vote-result';
	resultDiv.textContent = '';

	// Cancel handler
	const cancelHandler = () => {
		modal.classList.remove('show');
	};

	// Confirm handler
	const confirmHandler = async () => {
		const winningOption = (
			document.querySelector('input[name="winner-option"]:checked') as HTMLInputElement
		).value;

		confirmButton.disabled = true;
		cancelButton.disabled = true;
		resultDiv.className = 'vote-result loading show';
		resultDiv.textContent = 'Checking network...';

		try {
			// Check if on BSC Testnet
			const network = await provider!.getNetwork();
			const chainId = Number(network.chainId);

			if (chainId !== 97) {
				throw new Error(
					`Wrong network! Please switch MetaMask to BSC Testnet (Chain ID: 97).\n\nCurrent network: ${chainId}`
				);
			}

			resultDiv.textContent = 'Step 1/3: Preparing finish betting...';

			// Load contract ABI
			const contractAbiResponse = await fetch('/contract-abi.json');
			const contractAbi = await contractAbiResponse.json();

			// Step 1: Finish betting via API (to verify admin)
			const finishResponse = await fetch(`${API_BASE}/finish`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ marketId: MARKET_ID, adminAddress: userAddress }),
			});

			const finishData = await finishResponse.json();
			if (!finishData.success) {
				throw new Error(finishData.detail || 'Failed to prepare finish betting');
			}

			resultDiv.textContent = 'Step 1/3: Finishing betting (confirm transaction)...';

			// Send transaction via MetaMask
			const contract = new ethers.Contract(finishData.contractAddress, contractAbi, signer);
			const tx = await contract.finishBetting(MARKET_ID);

			resultDiv.textContent = 'Step 1/3: Waiting for transaction confirmation...';
			await tx.wait();

			resultDiv.textContent = 'Step 2/3: Calculating payouts...';

			// Step 2: Calculate payouts
			const payoutsResponse = await fetch(`${API_BASE}/calculate-payouts`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ marketId: MARKET_ID, winningOption }),
			});

			const payoutsData = await payoutsResponse.json();
			if (!payoutsData.success) {
				throw new Error(payoutsData.detail || 'Failed to calculate payouts');
			}

			resultDiv.textContent = 'Step 3/3: Setting payouts in contract (confirm transaction)...';

			// Step 3: Set payouts - batch them
			const payouts = payoutsData.payouts.filter((p: any) => p.payout > 0);
			const BATCH_SIZE = 20;
			const totalBatches = Math.ceil(payouts.length / BATCH_SIZE);

			for (let i = 0; i < payouts.length; i += BATCH_SIZE) {
				const batchNum = Math.floor(i / BATCH_SIZE) + 1;
				const batchAddresses = payouts.slice(i, i + BATCH_SIZE).map((p: any) => p.wallet);
				const batchAmounts = payouts.slice(i, i + BATCH_SIZE).map((p: any) => Math.floor(p.payout));
				const isLastBatch = (i + BATCH_SIZE) >= payouts.length;

				resultDiv.textContent = `Step 3/3: Setting payouts batch ${batchNum}/${totalBatches} (confirm transaction)...`;

				const tx = await contract.setPayouts(MARKET_ID, batchAddresses, batchAmounts, isLastBatch);

				resultDiv.textContent = `Step 3/3: Waiting for batch ${batchNum}/${totalBatches} confirmation...`;
				await tx.wait();
			}

			resultDiv.className = 'vote-result success show';
			resultDiv.innerHTML = `
        Prediction finished successfully!<br>
        <small>Winning option: ${winningOption}</small><br>
        <small>Winners: ${payoutsData.total_winners}</small><br>
        <small>Total pool: ${payoutsData.total_pool} wei</small><br>
        <small>Winners can now claim their payouts!</small>
      `;

			// Reload data
			setTimeout(() => {
				modal.classList.remove('show');
				loadMarketDetails();
				loadChart();
				finishButton.disabled = true;
				finishButton.textContent = 'Prediction Finished';
			}, 3000);
		} catch (error: any) {
			console.error('Finish prediction error:', error);
			resultDiv.className = 'vote-result error show';

			// Clean error message handling
			let errorMessage = 'Failed to finish prediction';

			if (error.code === 'ACTION_REJECTED' || error.code === 4001) {
				errorMessage = 'Transaction cancelled by user';
			} else if (error.message) {
				if (error.message.includes('user rejected')) {
					errorMessage = 'Transaction cancelled by user';
				} else if (error.message.includes('Not authorized')) {
					errorMessage = 'Not authorized: Admin only';
				} else if (error.message.includes('already finished')) {
					errorMessage = 'Betting already finished';
				} else if (error.message.includes('Wrong network')) {
					errorMessage = error.message;
				} else if (error.message.length < 100) {
					errorMessage = error.message;
				} else {
					errorMessage = 'Operation failed. Check console for details';
				}
			}

			resultDiv.textContent = `✗ ${errorMessage}`;
			confirmButton.disabled = false;
			cancelButton.disabled = false;
		}
	};

	// Add event listeners
	cancelButton.onclick = cancelHandler;
	confirmButton.onclick = confirmHandler;
}

// Initialize
async function init() {
	// Add back button
	const header = document.querySelector('.header')!;
	const backButton = document.createElement('a');
	backButton.href = '/markets.html';
	backButton.className = 'back-button';
	backButton.innerHTML = '← Back to Markets';
	backButton.style.cssText =
		'display: block; margin-bottom: 10px; color: var(--color-primary); text-decoration: none;';
	header.insertBefore(backButton, header.firstChild);

	await loadMarketDetails();
	await loadChart();

	// Initially hide finish button (will show if admin)
	updateFinishButtonVisibility();

	// Try to auto-reconnect if wallet was previously connected
	if (window.ethereum) {
		try {
			const accounts = await window.ethereum.request({ method: 'eth_accounts' });
			if (accounts.length > 0) {
				await connectWallet();
			}
		} catch (error) {
			console.log('Auto-reconnect not available');
		}
	}

	// Setup wallet connection
	const connectBtn = document.getElementById('wallet-connect-btn') as HTMLButtonElement;
	connectBtn.addEventListener('click', async () => {
		if (userAddress) {
			// Ask for confirmation before disconnecting
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

	// Setup form handler
	const form = document.getElementById('vote-form')!;
	form.addEventListener('submit', handleVoteSubmit);

	// Setup finish button
	const finishButton = document.getElementById('finish-button')!;
	finishButton.addEventListener('click', handleFinishPrediction);

	// Poll for updates every 5 seconds
	setInterval(() => {
		loadMarketDetails();
		loadChart();
	}, 5000);
}

// Start the app
init();
