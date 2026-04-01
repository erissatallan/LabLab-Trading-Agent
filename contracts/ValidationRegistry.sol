// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./AgentRegistry.sol";

/**
 * @title ValidationRegistry
 * @notice On-chain checkpoint attestation store for ERC-8004 agents.
 * The lablab.ai leaderboard reads validator scores from this registry.
 */
contract ValidationRegistry {

    enum ProofType { NONE, EIP712, TEE, ZKML }

    struct Attestation {
        uint256  agentId;
        address  validator;
        bytes32  checkpointHash;
        uint8    score;
        ProofType proofType;
        bytes    proof;
        string   notes;
        uint256  timestamp;
    }

    AgentRegistry public immutable agentRegistry;
    address public owner;
    bool public openValidation;

    mapping(address => bool) public validators;
    mapping(uint256 => Attestation[]) private _attestations;
    mapping(bytes32 => Attestation) public checkpointAttestations;
    mapping(uint256 => uint256) public attestationCount;

    event AttestationPosted(uint256 indexed agentId, address indexed validator, bytes32 indexed checkpointHash, uint8 score, ProofType proofType);
    event ValidatorAdded(address indexed validator);
    event ValidatorRemoved(address indexed validator);

    constructor(address agentRegistryAddress, bool _openValidation) {
        agentRegistry = AgentRegistry(agentRegistryAddress);
        owner = msg.sender;
        openValidation = _openValidation;
        validators[msg.sender] = true;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "ValidationRegistry: not owner");
        _;
    }

    modifier onlyValidator() {
        require(openValidation || validators[msg.sender], "ValidationRegistry: not an authorized validator");
        _;
    }

    function addValidator(address validator) external onlyOwner {
        validators[validator] = true;
        emit ValidatorAdded(validator);
    }

    function removeValidator(address validator) external onlyOwner {
        validators[validator] = false;
        emit ValidatorRemoved(validator);
    }

    function setOpenValidation(bool open) external onlyOwner {
        openValidation = open;
    }

    function postAttestation(
        uint256 agentId,
        bytes32 checkpointHash,
        uint8 score,
        ProofType proofType,
        bytes calldata proof,
        string calldata notes
    ) external onlyValidator {
        require(agentRegistry.isRegistered(agentId), "ValidationRegistry: agent not registered");
        require(checkpointHash != bytes32(0), "ValidationRegistry: checkpointHash required");
        require(score <= 100, "ValidationRegistry: score must be 0-100");

        Attestation memory attestation = Attestation({
            agentId: agentId,
            validator: msg.sender,
            checkpointHash: checkpointHash,
            score: score,
            proofType: proofType,
            proof: proof,
            notes: notes,
            timestamp: block.timestamp
        });

        _attestations[agentId].push(attestation);
        checkpointAttestations[checkpointHash] = attestation;
        attestationCount[agentId]++;

        emit AttestationPosted(agentId, msg.sender, checkpointHash, score, proofType);
    }

    function postEIP712Checkpoint(
        uint256 agentId,
        bytes32 checkpointHash,
        uint8 score,
        string calldata notes
    ) external onlyValidator {
        require(agentRegistry.isRegistered(agentId), "ValidationRegistry: agent not registered");
        require(checkpointHash != bytes32(0), "ValidationRegistry: checkpointHash required");
        require(score <= 100, "ValidationRegistry: score must be 0-100");

        Attestation memory attestation = Attestation({
            agentId: agentId,
            validator: msg.sender,
            checkpointHash: checkpointHash,
            score: score,
            proofType: ProofType.EIP712,
            proof: bytes(""),
            notes: notes,
            timestamp: block.timestamp
        });

        _attestations[agentId].push(attestation);
        checkpointAttestations[checkpointHash] = attestation;
        attestationCount[agentId]++;

        emit AttestationPosted(agentId, msg.sender, checkpointHash, score, ProofType.EIP712);
    }

    function getAttestations(uint256 agentId) external view returns (Attestation[] memory) {
        return _attestations[agentId];
    }

    function getAverageValidationScore(uint256 agentId) external view returns (uint256) {
        Attestation[] storage atts = _attestations[agentId];
        if (atts.length == 0) return 0;
        uint256 total = 0;
        for (uint256 i = 0; i < atts.length; i++) {
            total += atts[i].score;
        }
        return total / atts.length;
    }

    function getAttestation(bytes32 checkpointHash) external view returns (Attestation memory) {
        return checkpointAttestations[checkpointHash];
    }
}
