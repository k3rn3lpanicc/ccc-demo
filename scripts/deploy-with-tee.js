const hre = require('hardhat');
const fs = require('fs');
const axios = require('axios');

async function main() {
	console.log('Deploying PrivateBetting contract with TEE initialization...\n');

	console.log('> Requesting initial state from TEE...');

	let initialState;
	try {
		const response = await axios.get('http://127.0.0.1:8000/initialize_state');

		if (response.data.success) {
			initialState = response.data.encrypted_state;
			console.log('✓ Received encrypted state from TEE');
			console.log(`   State length: ${initialState.length} chars\n`);
		} else {
			console.error('X TEE initialization failed:', response.data.error);
			process.exit(1);
		}
	} catch (error) {
		console.error("X Could not connect to TEE. Make sure it's running:");
		console.error('   python tee.py');
		console.error('\nError:', error.message);
		process.exit(1);
	}

	console.log('> Deploying contract...');
	const PrivateBetting = await hre.ethers.getContractFactory('PrivateBetting');
	const contract = await PrivateBetting.deploy(initialState);

	await contract.waitForDeployment();

	const address = await contract.getAddress();
	console.log('✓ PrivateBetting deployed to:', address);

	// Save the address for later use
	const deploymentInfo = {
		address: address,
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
