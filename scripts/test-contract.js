const hre = require("hardhat");

async function main() {
  console.log("\n" + "=".repeat(60));
  console.log("TESTING SMART CONTRACT");
  console.log("=".repeat(60));

  // Get signers
  const [admin, voter1, voter2, voter3] = await hre.ethers.getSigners();
  
  console.log("\n1. Deploying contract...");
  const PrivateBetting = await hre.ethers.getContractFactory("PrivateBetting");
  const contract = await PrivateBetting.deploy("INITIAL_ENCRYPTED_STATE");
  await contract.waitForDeployment();
  const address = await contract.getAddress();
  
  console.log("   Contract deployed at:", address);
  console.log("   Admin:", admin.address);

  // Step 2: Submit votes
  console.log("\n2. Submitting votes...");
  
  const vote1Tx = await contract.connect(voter1).vote(
    "encrypted_vote_1",
    "encrypted_key_1",
    "capsule_1",
    { value: hre.ethers.parseEther("1.0") }
  );
  await vote1Tx.wait();
  console.log("   ✅ Voter 1 voted with 1 ETH");

  const vote2Tx = await contract.connect(voter2).vote(
    "encrypted_vote_2",
    "encrypted_key_2",
    "capsule_2",
    { value: hre.ethers.parseEther("2.0") }
  );
  await vote2Tx.wait();
  console.log("   ✅ Voter 2 voted with 2 ETH");

  const vote3Tx = await contract.connect(voter3).vote(
    "encrypted_vote_3",
    "encrypted_key_3",
    "capsule_3",
    { value: hre.ethers.parseEther("1.5") }
  );
  await vote3Tx.wait();
  console.log("   ✅ Voter 3 voted with 1.5 ETH");

  // Step 3: Check contract balance
  console.log("\n3. Contract status:");
  const balance = await hre.ethers.provider.getBalance(address);
  console.log("   Contract balance:", hre.ethers.formatEther(balance), "ETH");
  console.log("   Betting finished:", await contract.bettingFinished());

  // Step 4: Update state (simulating node processing)
  console.log("\n4. Updating state...");
  const updateTx = await contract.updateState("NEW_ENCRYPTED_STATE_AFTER_VOTES");
  await updateTx.wait();
  console.log("   ✅ State updated");

  // Step 5: Finish betting (admin only)
  console.log("\n5. Finishing betting...");
  const finishTx = await contract.connect(admin).finishBetting();
  await finishTx.wait();
  console.log("   ✅ Betting finished");
  console.log("   Status:", await contract.status());

  // Step 6: Set payouts (admin only)
  console.log("\n6. Setting payouts...");
  // Simulate: Voter 1 and 2 win, Voter 3 loses
  const winners = [voter1.address, voter2.address];
  const amounts = [
    hre.ethers.parseEther("1.5"), // Voter 1 gets 1.5 ETH
    hre.ethers.parseEther("3.0")  // Voter 2 gets 3.0 ETH
  ];
  
  const setPayoutsTx = await contract.connect(admin).setPayouts(winners, amounts);
  await setPayoutsTx.wait();
  console.log("   ✅ Payouts set");
  console.log("   Voter 1 payout:", hre.ethers.formatEther(await contract.getPayoutAmount(voter1.address)), "ETH");
  console.log("   Voter 2 payout:", hre.ethers.formatEther(await contract.getPayoutAmount(voter2.address)), "ETH");
  console.log("   Voter 3 payout:", hre.ethers.formatEther(await contract.getPayoutAmount(voter3.address)), "ETH");

  // Step 7: Claim payouts
  console.log("\n7. Claiming payouts...");
  
  const balanceBefore1 = await hre.ethers.provider.getBalance(voter1.address);
  const claim1Tx = await contract.connect(voter1).claimPayout();
  await claim1Tx.wait();
  const balanceAfter1 = await hre.ethers.provider.getBalance(voter1.address);
  console.log("   ✅ Voter 1 claimed (received ~", hre.ethers.formatEther(balanceAfter1 - balanceBefore1), "ETH)");

  const balanceBefore2 = await hre.ethers.provider.getBalance(voter2.address);
  const claim2Tx = await contract.connect(voter2).claimPayout();
  await claim2Tx.wait();
  const balanceAfter2 = await hre.ethers.provider.getBalance(voter2.address);
  console.log("   ✅ Voter 2 claimed (received ~", hre.ethers.formatEther(balanceAfter2 - balanceBefore2), "ETH)");

  // Step 8: Final status
  console.log("\n8. Final status:");
  const finalBalance = await hre.ethers.provider.getBalance(address);
  console.log("   Contract balance:", hre.ethers.formatEther(finalBalance), "ETH");
  console.log("   Voter 1 claimed:", await contract.hasClaimedPayout(voter1.address));
  console.log("   Voter 2 claimed:", await contract.hasClaimedPayout(voter2.address));
  console.log("   Voter 3 claimed:", await contract.hasClaimedPayout(voter3.address));

  console.log("\n" + "=".repeat(60));
  console.log("✅ TEST COMPLETED SUCCESSFULLY");
  console.log("=".repeat(60) + "\n");
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
