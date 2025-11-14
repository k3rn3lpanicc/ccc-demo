const hre = require("hardhat");
const fs = require('fs');

async function main() {
  console.log("Deploying PrivateBetting contract...");

  // Get the initial encrypted state from TEE
  // In production, you'd call the TEE's /initialize_state endpoint
  // For now, we'll use a placeholder
  const initialState = "PLACEHOLDER_ENCRYPTED_STATE";

  const PrivateBetting = await hre.ethers.getContractFactory("PrivateBetting");
  const contract = await PrivateBetting.deploy(initialState);

  await contract.waitForDeployment();

  const address = await contract.getAddress();
  console.log("PrivateBetting deployed to:", address);
  console.log("Admin address:", await contract.admin());

  // Save the address for later use
  const deploymentInfo = {
    address: address,
    deployer: await contract.admin(),
    timestamp: new Date().toISOString()
  };
  
  fs.writeFileSync(
    'contract-address.json',
    JSON.stringify(deploymentInfo, null, 2)
  );

  console.log("Contract address saved to contract-address.json");
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
