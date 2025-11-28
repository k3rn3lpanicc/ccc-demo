// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract PrivateBetting {
    address public admin;
    string public encryptedState;
    bool public bettingFinished;
    IERC20 public token;

    enum BettingStatus {
        Active,
        Finished,
        PayoutsSet
    }
    BettingStatus public status;

    // Mapping of wallet addresses to their payouts (set after betting finishes)
    mapping(address => uint256) public payouts;
    mapping(address => bool) public hasClaimed;

    // Events
    event VoteSubmitted(
        address indexed voter,
        string encryptedVote,
        string encryptedSymKey,
        string capsule,
        uint256 amount
    );

    event BettingFinished(string winningOption, string finalState);
    event PayoutsSet(uint256 totalWinners, uint256 totalPool);
    event PayoutClaimed(address indexed winner, uint256 amount);
    event StateUpdated(string newEncryptedState);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Only admin can call this");
        _;
    }

    modifier bettingActive() {
        require(status == BettingStatus.Active, "Betting is not active");
        _;
    }

    modifier bettingFinishedNotPaid() {
        require(
            status == BettingStatus.Finished,
            "Betting not finished or payouts already set"
        );
        _;
    }

    constructor(string memory _initialEncryptedState, address _tokenAddress) {
        admin = msg.sender;
        encryptedState = _initialEncryptedState;
        status = BettingStatus.Active;
        bettingFinished = false;
        token = IERC20(_tokenAddress);
    }

    /**
     * @dev User submits their encrypted vote along with tokens
     * @param encryptedVote Base64 encoded AES-encrypted vote
     * @param encryptedSymKey Base64 encoded threshold-encrypted symmetric key
     * @param capsule Base64 encoded Umbral capsule
     * @param amount Amount of tokens to bet
     */
    function vote(
        string memory encryptedVote,
        string memory encryptedSymKey,
        string memory capsule,
        uint256 amount
    ) external bettingActive {
        require(amount > 0, "Must bet a positive amount");

        // Transfer tokens from user to contract
        require(
            token.transferFrom(msg.sender, address(this), amount),
            "Token transfer failed"
        );

        // Emit event for nodes to listen to
        emit VoteSubmitted(
            msg.sender,
            encryptedVote,
            encryptedSymKey,
            capsule,
            amount
        );
    }

    /**
     * @dev Admin finishes the betting period
     * Can only be called once
     */
    function finishBetting() external onlyAdmin bettingActive {
        status = BettingStatus.Finished;
        bettingFinished = true;

        emit BettingFinished("", encryptedState);
    }

    /**
     * @dev Update the encrypted state (called by oracle/nodes after processing vote)
     * @param newEncryptedState The new encrypted state from TEE
     */
    function updateState(
        string memory newEncryptedState
    ) external bettingActive {
        // In production, you'd want to verify the caller is authorized (oracle/node)
        // For now, anyone can update during active betting
        encryptedState = newEncryptedState;

        emit StateUpdated(newEncryptedState);
    }

    /**
     * @dev Set payouts after TEE calculates them (supports batching)
     * @param winners Array of winner addresses
     * @param amounts Array of payout amounts (in wei)
     * @param isLastBatch True if this is the final batch
     */
    function setPayouts(
        address[] memory winners,
        uint256[] memory amounts,
        bool isLastBatch
    ) external onlyAdmin bettingFinishedNotPaid {
        require(winners.length == amounts.length, "Arrays length mismatch");

        for (uint256 i = 0; i < winners.length; i++) {
            payouts[winners[i]] = amounts[i];
        }

        if (isLastBatch) {
            status = BettingStatus.PayoutsSet;
            emit PayoutsSet(winners.length, 0);
        }
    }

    /**
     * @dev Winners claim their payouts
     */
    function claimPayout() external {
        require(status == BettingStatus.PayoutsSet, "Payouts not set yet");
        require(payouts[msg.sender] > 0, "No payout available");
        require(!hasClaimed[msg.sender], "Already claimed");

        uint256 amount = payouts[msg.sender];
        hasClaimed[msg.sender] = true;

        require(token.transfer(msg.sender, amount), "Token transfer failed");

        emit PayoutClaimed(msg.sender, amount);
    }

    /**
     * @dev Get the current encrypted state
     */
    function getCurrentState() external view returns (string memory) {
        return encryptedState;
    }

    /**
     * @dev Get payout amount for an address
     */
    function getPayoutAmount(address wallet) external view returns (uint256) {
        return payouts[wallet];
    }

    /**
     * @dev Check if an address has claimed their payout
     */
    function hasClaimedPayout(address wallet) external view returns (bool) {
        return hasClaimed[wallet];
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
