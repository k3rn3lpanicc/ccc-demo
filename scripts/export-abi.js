const fs = require('fs');
const path = require('path');

async function main() {
  // Read the compiled contract artifact
  const artifactPath = path.join(__dirname, '../artifacts/contracts/PrivateBetting.sol/PrivateBetting.json');
  
  if (!fs.existsSync(artifactPath)) {
    console.error('Contract not compiled. Run: npx hardhat compile');
    process.exit(1);
  }
  
  const artifact = JSON.parse(fs.readFileSync(artifactPath, 'utf8'));
  
  // Export just the ABI
  fs.writeFileSync(
    'contract-abi.json',
    JSON.stringify(artifact.abi, null, 2)
  );
  
  console.log('✅ Contract ABI exported to contract-abi.json');

  // Export Token ABI
  const tokenArtifactPath = path.join(__dirname, '../artifacts/contracts/MockUSDC.sol/MockUSDC.json');
  
  if (fs.existsSync(tokenArtifactPath)) {
    const tokenArtifact = JSON.parse(fs.readFileSync(tokenArtifactPath, 'utf8'));
    fs.writeFileSync(
      'token-abi.json',
      JSON.stringify(tokenArtifact.abi, null, 2)
    );
    console.log('✅ Token ABI exported to token-abi.json');
  } else {
    console.warn('⚠️  MockUSDC not compiled. Token ABI not exported.');
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
