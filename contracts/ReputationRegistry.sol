// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./AgentRegistry.sol";

/**
 * @title ReputationRegistry
 * @notice On-chain reputation accumulation for ERC-8004 agents.
 */
contract ReputationRegistry {

    struct FeedbackEntry {
        address rater;
        uint8   score;
        bytes32 outcomeRef;
        string  comment;
        uint256 timestamp;
        FeedbackType feedbackType;
    }

    enum FeedbackType { TRADE_EXECUTION, RISK_MANAGEMENT, STRATEGY_QUALITY, GENERAL }

    struct ReputationSummary {
        uint256 totalScore;
        uint256 feedbackCount;
        uint256 lastUpdated;
    }

    AgentRegistry public immutable agentRegistry;

    mapping(uint256 => ReputationSummary) public reputation;
    mapping(uint256 => FeedbackEntry[]) private _feedbackHistory;
    mapping(uint256 => mapping(address => bool)) private _hasRated;

    event FeedbackSubmitted(uint256 indexed agentId, address indexed rater, uint8 score, bytes32 outcomeRef, FeedbackType feedbackType);

    constructor(address agentRegistryAddress) {
        agentRegistry = AgentRegistry(agentRegistryAddress);
    }

    function submitFeedback(
        uint256 agentId,
        uint8 score,
        bytes32 outcomeRef,
        string calldata comment,
        FeedbackType feedbackType
    ) external {
        require(agentRegistry.isRegistered(agentId), "ReputationRegistry: agent not registered");
        require(score >= 1 && score <= 100, "ReputationRegistry: score must be 1-100");
        require(outcomeRef != bytes32(0), "ReputationRegistry: outcomeRef required");
        require(!_hasRated[agentId][msg.sender], "ReputationRegistry: already rated this agent");

        AgentRegistry.AgentRegistration memory reg = agentRegistry.getAgent(agentId);
        require(msg.sender != reg.operatorWallet, "ReputationRegistry: operator cannot self-rate");
        require(msg.sender != agentRegistry.ownerOf(agentId), "ReputationRegistry: owner cannot self-rate");
        require(msg.sender != reg.agentWallet, "ReputationRegistry: agent wallet cannot self-rate");

        _hasRated[agentId][msg.sender] = true;

        _feedbackHistory[agentId].push(FeedbackEntry({
            rater: msg.sender,
            score: score,
            outcomeRef: outcomeRef,
            comment: comment,
            timestamp: block.timestamp,
            feedbackType: feedbackType
        }));

        ReputationSummary storage rep = reputation[agentId];
        rep.totalScore += score;
        rep.feedbackCount++;
        rep.lastUpdated = block.timestamp;

        emit FeedbackSubmitted(agentId, msg.sender, score, outcomeRef, feedbackType);
    }

    function getAverageScore(uint256 agentId) external view returns (uint256) {
        ReputationSummary storage rep = reputation[agentId];
        if (rep.feedbackCount == 0) return 0;
        return rep.totalScore / rep.feedbackCount;
    }

    function getFeedbackHistory(uint256 agentId) external view returns (FeedbackEntry[] memory) {
        return _feedbackHistory[agentId];
    }

    function hasRated(uint256 agentId, address rater) external view returns (bool) {
        return _hasRated[agentId][rater];
    }
}
