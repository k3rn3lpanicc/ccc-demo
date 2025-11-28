// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";

contract PrivateBetting {
	using ECDSA for bytes32;
	using MessageHashUtils for bytes32;

	address public admin;
	address public teeAddress;
	IERC20 public token;
	uint256 public marketCount;

	enum BettingStatus {
		Active,
		Finished,
		PayoutsSet
	}

	struct Market {
		uint256 marketId;
		string title;
		string description;
		string encryptedState;
		BettingStatus status;
		bool bettingFinished;
		uint256 createdAt;
		uint256 totalVolume;
	}

	// Market ID => Market data
	mapping(uint256 => Market) public markets;

	// Market ID => voter => payout amount
	mapping(uint256 => mapping(address => uint256)) public payouts;

	// Market ID => voter => has claimed
	mapping(uint256 => mapping(address => bool)) public hasClaimed;

	// Events
	event MarketCreated(
		uint256 indexed marketId,
		string title,
		string description,
		uint256 createdAt
	);

	event VoteSubmitted(
		uint256 indexed marketId,
		address indexed voter,
		string encryptedVote,
		string encryptedSymKey,
		string capsule,
		uint256 amount
	);

	event BettingFinished(
		uint256 indexed marketId,
		string winningOption,
		string finalState
	);

	event PayoutsSet(
		uint256 indexed marketId,
		uint256 totalWinners,
		uint256 totalPool
	);

	event PayoutClaimed(
		uint256 indexed marketId,
		address indexed winner,
		uint256 amount
	);

	event StateUpdated(uint256 indexed marketId, string newEncryptedState);

	modifier onlyAdmin() {
		require(msg.sender == admin, "Only admin can call this");
		_;
	}

	modifier onlyTEE() {
		require(msg.sender == teeAddress, "Only TEE can call this");
		_;
	}

	modifier marketExists(uint256 marketId) {
		require(marketId < marketCount, "Market does not exist");
		_;
	}

	modifier bettingActive(uint256 marketId) {
		require(
			markets[marketId].status == BettingStatus.Active,
			"Betting is not active"
		);
		_;
	}

	modifier bettingFinishedNotPaid(uint256 marketId) {
		require(
			markets[marketId].status == BettingStatus.Finished,
			"Betting not finished or payouts already set"
		);
		_;
	}

	constructor(address _tokenAddress, address _teeAddress) {
		admin = msg.sender;
		token = IERC20(_tokenAddress);
		teeAddress = _teeAddress;
		marketCount = 0;
	}

	/**
	 * @dev Update TEE address (admin only)
	 */
	function setTEEAddress(address _teeAddress) external onlyAdmin {
		teeAddress = _teeAddress;
	}

	/**
	 * @dev Admin creates a new market
	 * @param title Market title
	 * @param description Market description
	 * @param initialEncryptedState Initial encrypted state from TEE
	 * @param signature TEE signature on ("", initialEncryptedState)
	 */
	function createMarket(
		string memory title,
		string memory description,
		string memory initialEncryptedState,
		bytes memory signature
	) external onlyAdmin returns (uint256) {
		// Verify the TEE signature on (empty -> initialState)
		require(
			verifyTEESignature("", initialEncryptedState, signature),
			"Invalid TEE signature for initial state"
		);

		uint256 marketId = marketCount;

		markets[marketId] = Market({
			marketId: marketId,
			title: title,
			description: description,
			encryptedState: initialEncryptedState,
			status: BettingStatus.Active,
			bettingFinished: false,
			createdAt: block.timestamp,
			totalVolume: 0
		});

		marketCount++;

		emit MarketCreated(marketId, title, description, block.timestamp);

		return marketId;
	}

	/**
	 * @dev User submits their encrypted vote along with tokens
	 * @param marketId Market ID to vote on
	 * @param encryptedVote Base64 encoded AES-encrypted vote
	 * @param encryptedSymKey Base64 encoded threshold-encrypted symmetric key
	 * @param capsule Base64 encoded Umbral capsule
	 * @param amount Amount of tokens to bet
	 */
	function vote(
		uint256 marketId,
		string memory encryptedVote,
		string memory encryptedSymKey,
		string memory capsule,
		uint256 amount
	) external marketExists(marketId) bettingActive(marketId) {
		require(amount > 0, "Must bet a positive amount");

		// Transfer tokens from user to contract
		require(
			token.transferFrom(msg.sender, address(this), amount),
			"Token transfer failed"
		);

		// Update market volume
		markets[marketId].totalVolume += amount;

		// Emit event for nodes to listen to
		emit VoteSubmitted(
			marketId,
			msg.sender,
			encryptedVote,
			encryptedSymKey,
			capsule,
			amount
		);
	}

	/**
	 * @dev Admin finishes the betting period for a market
	 * @param marketId Market ID to finish
	 */
	function finishBetting(
		uint256 marketId
	) external onlyAdmin marketExists(marketId) bettingActive(marketId) {
		markets[marketId].status = BettingStatus.Finished;
		markets[marketId].bettingFinished = true;

		emit BettingFinished(marketId, "", markets[marketId].encryptedState);
	}

	/**
	 * @dev Verify TEE signature on state transition
	 * @param prevState Previous encrypted state
	 * @param newState New encrypted state
	 * @param signature Signature from TEE
	 * @return bool True if signature is valid
	 */
	function verifyTEESignature(
		string memory prevState,
		string memory newState,
		bytes memory signature
	) public view returns (bool) {
		// Create the same message hash that TEE signed
		bytes32 messageHash = keccak256(abi.encodePacked(prevState, newState));

		// Recover the signer address from the signature
		address signer = messageHash.toEthSignedMessageHash().recover(
			signature
		);

		// Check if the signer is the TEE address
		return signer == teeAddress;
	}

	/**
	 * @dev Update the encrypted state (called by oracle/nodes after processing vote)
	 * @param marketId Market ID
	 * @param newEncryptedState The new encrypted state from TEE
	 * @param signature Signature from TEE proving state transition
	 */
	function updateState(
		uint256 marketId,
		string memory newEncryptedState,
		bytes memory signature
	) external marketExists(marketId) bettingActive(marketId) {
		// Get the previous state
		string memory prevState = markets[marketId].encryptedState;

		// Verify the TEE signature on (prevState, newState)
		require(
			verifyTEESignature(prevState, newEncryptedState, signature),
			"Invalid TEE signature"
		);

		// Update the state
		markets[marketId].encryptedState = newEncryptedState;

		emit StateUpdated(marketId, newEncryptedState);
	}

	/**
	 * @dev Set payouts after TEE calculates them (supports batching)
	 * @param marketId Market ID
	 * @param winners Array of winner addresses
	 * @param amounts Array of payout amounts (in wei)
	 * @param isLastBatch True if this is the final batch
	 */
	function setPayouts(
		uint256 marketId,
		address[] memory winners,
		uint256[] memory amounts,
		bool isLastBatch
	)
		external
		onlyAdmin
		marketExists(marketId)
		bettingFinishedNotPaid(marketId)
	{
		require(winners.length == amounts.length, "Arrays length mismatch");

		for (uint256 i = 0; i < winners.length; i++) {
			payouts[marketId][winners[i]] = amounts[i];
		}

		if (isLastBatch) {
			markets[marketId].status = BettingStatus.PayoutsSet;
			emit PayoutsSet(marketId, winners.length, 0);
		}
	}

	/**
	 * @dev Winners claim their payouts for a specific market
	 * @param marketId Market ID
	 */
	function claimPayout(uint256 marketId) external marketExists(marketId) {
		require(
			markets[marketId].status == BettingStatus.PayoutsSet,
			"Payouts not set yet"
		);
		require(payouts[marketId][msg.sender] > 0, "No payout available");
		require(!hasClaimed[marketId][msg.sender], "Already claimed");

		uint256 amount = payouts[marketId][msg.sender];
		hasClaimed[marketId][msg.sender] = true;

		require(token.transfer(msg.sender, amount), "Token transfer failed");

		emit PayoutClaimed(marketId, msg.sender, amount);
	}

	/**
	 * @dev Get the current encrypted state for a market
	 * @param marketId Market ID
	 */
	function getCurrentState(
		uint256 marketId
	) external view marketExists(marketId) returns (string memory) {
		return markets[marketId].encryptedState;
	}

	/**
	 * @dev Get market details
	 * @param marketId Market ID
	 */
	function getMarket(
		uint256 marketId
	) external view marketExists(marketId) returns (Market memory) {
		return markets[marketId];
	}

	/**
	 * @dev Get all market IDs (for listing)
	 */
	function getAllMarketIds() external view returns (uint256[] memory) {
		uint256[] memory ids = new uint256[](marketCount);
		for (uint256 i = 0; i < marketCount; i++) {
			ids[i] = i;
		}
		return ids;
	}

	/**
	 * @dev Get payout amount for an address in a specific market
	 * @param marketId Market ID
	 * @param wallet Wallet address
	 */
	function getPayoutAmount(
		uint256 marketId,
		address wallet
	) external view marketExists(marketId) returns (uint256) {
		return payouts[marketId][wallet];
	}

	/**
	 * @dev Check if an address has claimed their payout for a market
	 * @param marketId Market ID
	 * @param wallet Wallet address
	 */
	function hasClaimedPayout(
		uint256 marketId,
		address wallet
	) external view marketExists(marketId) returns (bool) {
		return hasClaimed[marketId][wallet];
	}

	/**
	 * @dev Get contract token balance
	 */
	function getContractBalance() external view returns (uint256) {
		return token.balanceOf(address(this));
	}

	/**
	 * @dev Get token address
	 */
	function getTokenAddress() external view returns (address) {
		return address(token);
	}
}
