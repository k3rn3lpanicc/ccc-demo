const hre = require('hardhat');
const fs = require('fs');
const axios = require('axios');

async function main() {
	console.log('Deploying MockUSDC and PrivateBetting contracts with TEE initialization...\n');

	// Deploy MockUSDC token first
	console.log('> Deploying MockUSDC token...');
	const MockUSDC = await hre.ethers.getContractFactory('MockUSDC');
	const usdc = await MockUSDC.deploy();
	await usdc.waitForDeployment();

	const usdcAddress = await usdc.getAddress();
	console.log('✓ MockUSDC deployed to:', usdcAddress);

	// Get deployer and mint tokens to test accounts
	const [deployer] = await hre.ethers.getSigners();
	const deployerBalance = await usdc.balanceOf(deployer.address);
	console.log(`   Deployer balance: ${hre.ethers.formatUnits(deployerBalance, 18)} USDC\n`);

	// Mint USDC to accounts 1-50 for testing (10,000 USDC each)
	console.log('> Minting USDC to test accounts (1-50)...');
	const accounts = await hre.ethers.getSigners();
	for (let i = 1; i <= 50 && i < accounts.length; i++) {
		const mintAmount = hre.ethers.parseUnits('10000', 18);
		await usdc.mint(accounts[i].address, mintAmount);
		if (i % 10 === 0) {
			console.log(`   Minted to ${i} accounts...`);
		}
	}
	console.log('✓ Minted 10,000 USDC to 50 test accounts\n');

	// Get TEE address first
	console.log('> Getting TEE signing address...');
	let teeAddress;
	try {
		const teeResponse = await axios.get('http://127.0.0.1:8000/tee_address');
		if (teeResponse.data.success) {
			teeAddress = teeResponse.data.address;
			console.log('✓ TEE Address:', teeAddress);
		} else {
			console.error('X Failed to get TEE address');
			process.exit(1);
		}
	} catch (error) {
		console.error("X Could not connect to TEE. Make sure it's running:");
		console.error('   python -m uvicorn tee:app');
		console.error('\nError:', error.message);
		process.exit(1);
	}

	console.log('\n> Requesting initial state from TEE...');

	let initialState, initialSignature;
	try {
		const response = await axios.get('http://127.0.0.1:8000/initialize_state');

		if (response.data.success) {
			initialState = response.data.encrypted_state;
			initialSignature = response.data.signature;
			console.log('✓ Received encrypted state from TEE');
			console.log(`   State length: ${initialState.length} chars`);
			console.log(`   Signature: ${initialSignature.substring(0, 20)}...\n`);
		} else {
			console.error('X TEE initialization failed:', response.data.error);
			process.exit(1);
		}
	} catch (error) {
		console.error("X Could not connect to TEE. Make sure it's running:");
		console.error('   python -m uvicorn tee:app');
		console.error('\nError:', error.message);
		process.exit(1);
	}

	console.log('> Deploying PrivateBetting contract...');
	const PrivateBetting = await hre.ethers.getContractFactory('PrivateBetting');
	const contract = await PrivateBetting.deploy(teeAddress);

	await contract.waitForDeployment();

	const address = await contract.getAddress();
	console.log('✓ PrivateBetting deployed to:', address);
	
	// Create a default market for testing
	console.log('\n> Creating default test market...');
	
	// Ensure signature has 0x prefix for ethers.js
	const signatureBytes = initialSignature.startsWith('0x') 
		? initialSignature 
		: '0x' + initialSignature;
	
	const createMarketTx = await contract.createMarket(
		'Will ETH reach $10,000 by end of 2025?',
		'A prediction market on whether Ethereum will reach $10,000 USD by December 31, 2025.',
		usdcAddress,
		initialState,
		signatureBytes
	);
	await createMarketTx.wait();
	console.log('✓ Default market created (ID: 0)');
	console.log(`   Market token: ${usdcAddress} (USDC)\n`);

	// Save the addresses for later use
	const deploymentInfo = {
		address: address,
		tokenAddress: usdcAddress,
		teeAddress: teeAddress,
		deployer: await contract.admin(),
		timestamp: new Date().toISOString(),
	};

	fs.writeFileSync('contract-address.json', JSON.stringify(deploymentInfo, null, 2));
}

main()
	.then(() => process.exit(0))
	.catch((error) => {
		console.error(error);
		process.exit(1);
	});
