import './style.css';

const API_BASE = 'http://127.0.0.1:3001/api';

interface Market {
	marketId: number;
	title: string;
	description: string;
	status: number;
	bettingFinished: boolean;
	createdAt: number;
	totalVolume: number;
}

let isAdmin = false;
let adminAddress = '';

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
					<span class="stat-value">${market.totalVolume.toFixed(2)} USDC</span>
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

// Handle create market form
document.getElementById('create-market-form')!.addEventListener('submit', async (e) => {
	e.preventDefault();

	const title = (document.getElementById('market-title') as HTMLInputElement).value;
	const description = (document.getElementById('market-description') as HTMLTextAreaElement).value;
	const resultDiv = document.getElementById('create-result')!;
	const button = document.getElementById('create-market-button') as HTMLButtonElement;

	if (!isAdmin || !adminAddress) {
		resultDiv.textContent = '✗ Not authorized: Please login as admin';
		resultDiv.className = 'vote-result error show';
		return;
	}

	button.disabled = true;
	resultDiv.textContent = 'Creating market...';
	resultDiv.className = 'vote-result';

	try {
		const response = await fetch(`${API_BASE}/markets/create`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
			},
			body: JSON.stringify({ 
				title, 
				description,
				adminAddress 
			}),
		});

		const data = await response.json();

		if (data.success) {
			resultDiv.textContent = `✓ Market created successfully! (ID: ${data.marketId})`;
			resultDiv.className = 'vote-result success';
			
			// Clear form
			(document.getElementById('market-title') as HTMLInputElement).value = '';
			(document.getElementById('market-description') as HTMLTextAreaElement).value = '';

			// Reload markets
			setTimeout(() => {
				loadMarkets();
				resultDiv.textContent = '';
			}, 2000);
		} else {
			resultDiv.textContent = `✗ Failed: ${data.error || 'Unknown error'}`;
			resultDiv.className = 'vote-result error';
		}
	} catch (error) {
		resultDiv.textContent = `✗ Error: ${error}`;
		resultDiv.className = 'vote-result error';
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

// Admin login modal
function showLoginModal() {
	const modal = document.getElementById('admin-login-modal')!;
	modal.classList.add('show');
}

document.getElementById('cancel-login')!.addEventListener('click', () => {
	const modal = document.getElementById('admin-login-modal')!;
	modal.classList.remove('show');
});

document.getElementById('confirm-login')!.addEventListener('click', async () => {
	const addressInput = document.getElementById('admin-address') as HTMLInputElement;
	const resultDiv = document.getElementById('login-result')!;
	const confirmBtn = document.getElementById('confirm-login') as HTMLButtonElement;

	const inputAddress = addressInput.value.trim();

	if (!inputAddress || !inputAddress.startsWith('0x')) {
		resultDiv.textContent = '✗ Invalid address format';
		resultDiv.className = 'vote-result error show';
		return;
	}

	confirmBtn.disabled = true;
	resultDiv.textContent = 'Verifying...';
	resultDiv.className = 'vote-result loading show';

	try {
		const response = await fetch(`${API_BASE}/admin/verify`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
			},
			body: JSON.stringify({ address: inputAddress }),
		});

		const data = await response.json();

		if (data.success && data.isAdmin) {
			resultDiv.textContent = '✓ Admin verified!';
			resultDiv.className = 'vote-result success show';
			
			// Save to localStorage
			localStorage.setItem('adminAddress', inputAddress);
			isAdmin = true;
			adminAddress = inputAddress;

			setTimeout(() => {
				const modal = document.getElementById('admin-login-modal')!;
				modal.classList.remove('show');
				updateUIForAdmin();
				resultDiv.textContent = '';
				addressInput.value = '';
			}, 1000);
		} else {
			resultDiv.textContent = '✗ Not an admin address';
			resultDiv.className = 'vote-result error show';
		}
	} catch (error) {
		resultDiv.textContent = `✗ Error: ${error}`;
		resultDiv.className = 'vote-result error show';
	} finally {
		confirmBtn.disabled = false;
	}
});

// Initial load
checkAdminStatus();
loadMarkets();

// Refresh markets every 10 seconds
setInterval(loadMarkets, 10000);
