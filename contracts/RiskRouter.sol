// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "./AgentRegistry.sol";

/**
 * @title RiskRouter
 * @notice Enforces per-agent risk rules via EIP-712 signed TradeIntents.
 */
contract RiskRouter is EIP712 {

    struct TradeIntent {
        uint256 agentId;
        address agentWallet;
        string  pair;
        string  action;
        uint256 amountUsdScaled;
        uint256 maxSlippageBps;
        uint256 nonce;
        uint256 deadline;
    }

    struct RiskParams {
        uint256 maxPositionUsdScaled;
        uint256 maxDrawdownBps;
        uint256 maxTradesPerHour;
        bool    active;
    }

    struct TradeRecord {
        uint256 count;
        uint256 windowStart;
    }

    bytes32 public constant TRADE_INTENT_TYPEHASH = keccak256(
        "TradeIntent(uint256 agentId,address agentWallet,string pair,string action,"
        "uint256 amountUsdScaled,uint256 maxSlippageBps,uint256 nonce,uint256 deadline)"
    );

    address public owner;
    AgentRegistry public immutable agentRegistry;

    mapping(uint256 => RiskParams)  public riskParams;
    mapping(uint256 => TradeRecord) private _tradeRecords;
    mapping(uint256 => uint256)     private _intentNonces;

    event TradeIntentSubmitted(uint256 indexed agentId, bytes32 indexed intentHash, string pair, string action, uint256 amountUsdScaled);
    event TradeApproved(uint256 indexed agentId, bytes32 indexed intentHash, uint256 amountUsdScaled);
    event TradeRejected(uint256 indexed agentId, bytes32 indexed intentHash, string reason);
    event RiskParamsSet(uint256 indexed agentId, uint256 maxPositionUsdScaled, uint256 maxTradesPerHour);

    constructor(address agentRegistryAddress)
        EIP712("RiskRouter", "1")
    {
        owner = msg.sender;
        agentRegistry = AgentRegistry(agentRegistryAddress);
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "RiskRouter: not owner");
        _;
    }

    function setRiskParams(
        uint256 agentId,
        uint256 maxPositionUsdScaled,
        uint256 maxDrawdownBps,
        uint256 maxTradesPerHour
    ) external onlyOwner {
        require(maxPositionUsdScaled > 0, "RiskRouter: invalid maxPosition");
        require(maxDrawdownBps <= 10000, "RiskRouter: drawdown cannot exceed 100%");
        require(maxTradesPerHour > 0, "RiskRouter: invalid maxTradesPerHour");

        riskParams[agentId] = RiskParams({
            maxPositionUsdScaled: maxPositionUsdScaled,
            maxDrawdownBps: maxDrawdownBps,
            maxTradesPerHour: maxTradesPerHour,
            active: true
        });

        emit RiskParamsSet(agentId, maxPositionUsdScaled, maxTradesPerHour);
    }

    function submitTradeIntent(
        TradeIntent calldata intent,
        bytes calldata signature
    ) external returns (bool approved, string memory reason) {
        bytes32 intentHash = _hashTradeIntent(intent);

        emit TradeIntentSubmitted(intent.agentId, intentHash, intent.pair, intent.action, intent.amountUsdScaled);

        if (block.timestamp > intent.deadline) {
            emit TradeRejected(intent.agentId, intentHash, "Intent expired");
            return (false, "Intent expired");
        }

        if (intent.nonce != _intentNonces[intent.agentId]) {
            emit TradeRejected(intent.agentId, intentHash, "Invalid nonce");
            return (false, "Invalid nonce");
        }

        AgentRegistry.AgentRegistration memory reg = agentRegistry.getAgent(intent.agentId);
        require(intent.agentWallet == reg.agentWallet, "RiskRouter: agentWallet mismatch");

        bytes32 digest = _hashTypedDataV4(
            keccak256(abi.encode(
                TRADE_INTENT_TYPEHASH,
                intent.agentId,
                intent.agentWallet,
                keccak256(bytes(intent.pair)),
                keccak256(bytes(intent.action)),
                intent.amountUsdScaled,
                intent.maxSlippageBps,
                intent.nonce,
                intent.deadline
            ))
        );
        address recovered = ECDSA.recover(digest, signature);
        if (recovered != reg.agentWallet) {
            emit TradeRejected(intent.agentId, intentHash, "Invalid signature");
            return (false, "Invalid signature");
        }

        (approved, reason) = _validateRisk(intent.agentId, intent.amountUsdScaled);
        if (!approved) {
            emit TradeRejected(intent.agentId, intentHash, reason);
            return (false, reason);
        }

        _intentNonces[intent.agentId]++;
        _recordTrade(intent.agentId);

        emit TradeApproved(intent.agentId, intentHash, intent.amountUsdScaled);
        return (true, "");
    }

    function simulateIntent(
        TradeIntent calldata intent
    ) external view returns (bool approved, string memory reason) {
        if (block.timestamp > intent.deadline) return (false, "Intent expired");
        if (intent.nonce != _intentNonces[intent.agentId]) return (false, "Invalid nonce");
        return _validateRisk(intent.agentId, intent.amountUsdScaled);
    }

    function _validateRisk(uint256 agentId, uint256 amountUsdScaled) internal view returns (bool, string memory) {
        RiskParams storage params = riskParams[agentId];
        if (!params.active) {
            if (amountUsdScaled > 100000) return (false, "No risk params: exceeds $1000 default cap");
        } else {
            if (amountUsdScaled > params.maxPositionUsdScaled) return (false, "Exceeds maxPositionSize");
            TradeRecord storage record = _tradeRecords[agentId];
            uint256 currentCount = (block.timestamp >= record.windowStart + 1 hours) ? 0 : record.count;
            if (currentCount >= params.maxTradesPerHour) return (false, "Exceeds maxTradesPerHour");
        }
        return (true, "");
    }

    function _recordTrade(uint256 agentId) internal {
        TradeRecord storage record = _tradeRecords[agentId];
        if (block.timestamp >= record.windowStart + 1 hours) {
            record.windowStart = block.timestamp;
            record.count = 1;
        } else {
            record.count++;
        }
    }

    function _hashTradeIntent(TradeIntent calldata intent) internal pure returns (bytes32) {
        return keccak256(abi.encode(
            intent.agentId,
            intent.agentWallet,
            keccak256(bytes(intent.pair)),
            keccak256(bytes(intent.action)),
            intent.amountUsdScaled,
            intent.nonce,
            intent.deadline
        ));
    }

    function getIntentNonce(uint256 agentId) external view returns (uint256) {
        return _intentNonces[agentId];
    }

    function getTradeRecord(uint256 agentId) external view returns (uint256 count, uint256 windowStart) {
        TradeRecord storage r = _tradeRecords[agentId];
        return (r.count, r.windowStart);
    }

    function domainSeparator() external view returns (bytes32) {
        return _domainSeparatorV4();
    }
}
