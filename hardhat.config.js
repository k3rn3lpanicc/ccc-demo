require('@nomicfoundation/hardhat-toolbox');

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
	solidity: '0.8.20',
	networks: {
		hardhat: {
			chainId: 1337,
			accounts: {
				mnemonic: 'test test test test test test test test test test test junk',
				count: 50,
				initialIndex: 0,
				path: "m/44'/60'/0'/0",
				accountsBalance: '10000000000000000000000',
			},
		},
		localhost: {
			url: 'http://127.0.0.1:8545',
		},
	},
};
