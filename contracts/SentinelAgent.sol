// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title ISentinelIdentityRegistry
 * @notice Interface for the ERC-8004 Identity Registry
 * @dev Agents are represented as ERC-721 NFTs with metadata URIs
 */
interface IIdentityRegistry {
    function registerAgent(string calldata agentURI) external returns (uint256 agentId);
    function updateAgentURI(uint256 agentId, string calldata newURI) external;
    function getAgentURI(uint256 agentId) external view returns (string memory);
    function ownerOf(uint256 agentId) external view returns (address);
}

/**
 * @title IReputationRegistry
 * @dev Standardized feedback interface for agent reputation
 */
interface IReputationRegistry {
    struct Feedback {
        uint256 agentId;
        address reviewer;
        uint8 score;          // 1-5
        string tag;           // e.g., "profitable", "risk_compliant"
        string detailsURI;    // IPFS URI with detailed feedback
        uint256 timestamp;
    }
    
    function submitFeedback(uint256 agentId, uint8 score, string calldata tag, string calldata detailsURI) external;
    function getAverageScore(uint256 agentId) external view returns (uint256);
    function getFeedbackCount(uint256 agentId) external view returns (uint256);
}

/**
 * @title IValidationRegistry
 * @dev Records validation artifacts proving agent work
 */
interface IValidationRegistry {
    struct ValidationArtifact {
        uint256 agentId;
        string artifactType;   // "trade_intent", "risk_check", "compliance_report"
        string artifactURI;    // IPFS URI with the artifact data
        bytes32 artifactHash;  // keccak256 of the artifact content
        uint256 timestamp;
    }
    
    function submitArtifact(
        uint256 agentId,
        string calldata artifactType,
        string calldata artifactURI,
        bytes32 artifactHash
    ) external returns (uint256 artifactId);
    
    function getArtifact(uint256 artifactId) external view returns (ValidationArtifact memory);
    function getAgentArtifactCount(uint256 agentId) external view returns (uint256);
}

/**
 * @title SentinelAgent
 * @notice Sentinel's on-chain identity and validation contract
 * @dev Interacts with ERC-8004 registries for identity, reputation, and validation
 * 
 * Deployed on Base L2 for low gas costs.
 * 
 * Flow:
 * 1. Register agent identity (mint NFT with metadata)
 * 2. Before each trade: submit trade_intent validation artifact
 * 3. After each trade: submit risk_check validation artifact
 * 4. Periodically: submit compliance_report validation artifact
 */
contract SentinelAgent {
    // Registry addresses (set at deployment)
    IIdentityRegistry public identityRegistry;
    IReputationRegistry public reputationRegistry;
    IValidationRegistry public validationRegistry;
    
    // Agent state
    address public owner;
    uint256 public agentId;
    bool public isRegistered;
    
    // Validation tracking
    uint256 public totalArtifacts;
    mapping(uint256 => uint256) public artifactIds; // local index => registry artifact ID

    // Events
    event AgentRegistered(uint256 indexed agentId, string agentURI);
    event TradeIntentSubmitted(uint256 indexed artifactId, bytes32 artifactHash);
    event RiskCheckSubmitted(uint256 indexed artifactId, bytes32 artifactHash);
    event ComplianceReportSubmitted(uint256 indexed artifactId, bytes32 artifactHash);

    modifier onlyOwner() {
        require(msg.sender == owner, "SentinelAgent: caller is not owner");
        _;
    }

    modifier onlyRegistered() {
        require(isRegistered, "SentinelAgent: agent not registered");
        _;
    }

    constructor(
        address _identityRegistry,
        address _reputationRegistry,
        address _validationRegistry
    ) {
        owner = msg.sender;
        identityRegistry = IIdentityRegistry(_identityRegistry);
        reputationRegistry = IReputationRegistry(_reputationRegistry);
        validationRegistry = IValidationRegistry(_validationRegistry);
    }

    /**
     * @notice Register the agent on the Identity Registry
     * @param agentURI IPFS URI pointing to the Agent Card JSON
     */
    function register(string calldata agentURI) external onlyOwner {
        require(!isRegistered, "SentinelAgent: already registered");
        agentId = identityRegistry.registerAgent(agentURI);
        isRegistered = true;
        emit AgentRegistered(agentId, agentURI);
    }

    /**
     * @notice Update the agent's metadata URI
     * @param newURI Updated IPFS URI
     */
    function updateMetadata(string calldata newURI) external onlyOwner onlyRegistered {
        identityRegistry.updateAgentURI(agentId, newURI);
    }

    /**
     * @notice Submit a trade intent validation artifact
     * @param artifactURI IPFS URI with trade intent details
     * @param artifactHash keccak256 hash of the artifact content
     */
    function submitTradeIntent(
        string calldata artifactURI,
        bytes32 artifactHash
    ) external onlyOwner onlyRegistered returns (uint256) {
        uint256 artId = validationRegistry.submitArtifact(
            agentId, "trade_intent", artifactURI, artifactHash
        );
        artifactIds[totalArtifacts] = artId;
        totalArtifacts++;
        emit TradeIntentSubmitted(artId, artifactHash);
        return artId;
    }

    /**
     * @notice Submit a risk check validation artifact
     * @param artifactURI IPFS URI with risk check details
     * @param artifactHash keccak256 hash of the artifact content
     */
    function submitRiskCheck(
        string calldata artifactURI,
        bytes32 artifactHash
    ) external onlyOwner onlyRegistered returns (uint256) {
        uint256 artId = validationRegistry.submitArtifact(
            agentId, "risk_check", artifactURI, artifactHash
        );
        artifactIds[totalArtifacts] = artId;
        totalArtifacts++;
        emit RiskCheckSubmitted(artId, artifactHash);
        return artId;
    }

    /**
     * @notice Submit a compliance report validation artifact
     * @param artifactURI IPFS URI with compliance report
     * @param artifactHash keccak256 hash of the artifact content
     */
    function submitComplianceReport(
        string calldata artifactURI,
        bytes32 artifactHash
    ) external onlyOwner onlyRegistered returns (uint256) {
        uint256 artId = validationRegistry.submitArtifact(
            agentId, "compliance_report", artifactURI, artifactHash
        );
        artifactIds[totalArtifacts] = artId;
        totalArtifacts++;
        emit ComplianceReportSubmitted(artId, artifactHash);
        return artId;
    }

    /**
     * @notice Get the agent's current reputation score
     */
    function getReputation() external view onlyRegistered returns (uint256 avgScore, uint256 feedbackCount) {
        avgScore = reputationRegistry.getAverageScore(agentId);
        feedbackCount = reputationRegistry.getFeedbackCount(agentId);
    }
}
