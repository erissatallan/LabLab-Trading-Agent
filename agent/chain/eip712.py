"""
eip712.py — EIP-712 typed data signing for Sentinel trade decisions.

Implements:
- TradeIntent signing (submitted to RiskRouter on-chain)
- TradeCheckpoint signing (stored in checkpoints.jsonl + ValidationRegistry)

Chain: Base Sepolia (chainId=84532)
Domain: "RiskRouter" version "1" for TradeIntent
        "SentinelAgent" version "1" for checkpoints
"""

import json
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional

from eth_account import Account
from eth_account.messages import encode_typed_data

log = logging.getLogger(__name__)

# Base Sepolia chain ID
BASE_SEPOLIA_CHAIN_ID = 84532


# ────────────────────────────────────────────────────────────────────────────
# TradeIntent — matches RiskRouter.sol struct EXACTLY
# ────────────────────────────────────────────────────────────────────────────

TRADE_INTENT_TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "TradeIntent": [
        {"name": "agentId", "type": "uint256"},
        {"name": "agentWallet", "type": "address"},
        {"name": "pair", "type": "string"},
        {"name": "action", "type": "string"},
        {"name": "amountUsdScaled", "type": "uint256"},
        {"name": "maxSlippageBps", "type": "uint256"},
        {"name": "nonce", "type": "uint256"},
        {"name": "deadline", "type": "uint256"},
    ],
}


# ────────────────────────────────────────────────────────────────────────────
# TradeCheckpoint — signed record stored in checkpoints.jsonl
# ────────────────────────────────────────────────────────────────────────────

TRADE_CHECKPOINT_TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
    ],
    "TradeCheckpoint": [
        {"name": "agentId", "type": "uint256"},
        {"name": "sequenceNumber", "type": "uint256"},
        {"name": "symbol", "type": "string"},
        {"name": "signal", "type": "string"},
        {"name": "strategy", "type": "string"},
        {"name": "regime", "type": "string"},
        {"name": "confidence", "type": "uint256"},      # int(confidence * 100)
        {"name": "entryPriceScaled", "type": "uint256"}, # int(price * 100)
        {"name": "reasoningHash", "type": "bytes32"},   # keccak256 of reasoning string
        {"name": "timestamp", "type": "uint256"},
    ],
}


@dataclass
class TradeIntent:
    """Maps 1:1 to RiskRouter.TradeIntent struct."""
    agentId: int
    agentWallet: str
    pair: str          # e.g. "XBTUSD"
    action: str        # "BUY" or "SELL"
    amountUsdScaled: int  # USD * 100
    maxSlippageBps: int   # e.g. 100 = 1%
    nonce: int
    deadline: int      # unix timestamp


@dataclass
class TradeCheckpoint:
    """EIP-712 signed checkpoint for every trade decision."""
    agentId: int
    sequenceNumber: int
    symbol: str
    signal: str        # BUY / SELL / HOLD
    strategy: str
    regime: str
    confidence: int    # int(confidence * 100), e.g. 85 = 85%
    entryPriceScaled: int  # int(price * 100)
    reasoningHash: bytes  # keccak256 of reasoning string (bytes32)
    timestamp: int


class EIP712Signer:
    """
    Signs TradeIntent and TradeCheckpoint structs using EIP-712.

    Usage:
        signer = EIP712Signer(
            agent_wallet_private_key="0x...",
            risk_router_address="0x...",
            chain_id=84532,
        )
        intent, sig = signer.sign_trade_intent(...)
        checkpoint, sig = signer.sign_checkpoint(...)
    """

    def __init__(
        self,
        agent_wallet_private_key: str,
        risk_router_address: str,
        chain_id: int = BASE_SEPOLIA_CHAIN_ID,
    ):
        self.account = Account.from_key(agent_wallet_private_key)
        self.agent_wallet = self.account.address
        self.risk_router_address = risk_router_address
        self.chain_id = chain_id
        log.info(f"[eip712] Signer ready | wallet={self.agent_wallet[:10]}... | chainId={chain_id}")

    def sign_trade_intent(
        self,
        agent_id: int,
        pair: str,
        action: str,
        amount_usd: float,
        nonce: int,
        slippage_bps: int = 100,
        deadline_seconds: int = 300,
    ) -> tuple[TradeIntent, str]:
        """
        Sign a TradeIntent for submission to RiskRouter.submitTradeIntent().

        Args:
            agent_id: ERC-721 token ID
            pair: trading pair e.g. "XBTUSD"
            action: "BUY" or "SELL"
            amount_usd: trade size in USD (e.g. 500.00)
            nonce: current nonce from RiskRouter.getIntentNonce(agentId)
            slippage_bps: max slippage in basis points
            deadline_seconds: seconds from now until intent expires

        Returns:
            (TradeIntent, hex_signature)
        """
        amount_scaled = int(amount_usd * 100)
        deadline = int(time.time()) + deadline_seconds

        intent = TradeIntent(
            agentId=agent_id,
            agentWallet=self.agent_wallet,
            pair=pair,
            action=action.upper(),
            amountUsdScaled=amount_scaled,
            maxSlippageBps=slippage_bps,
            nonce=nonce,
            deadline=deadline,
        )

        domain = {
            "name": "RiskRouter",
            "version": "1",
            "chainId": self.chain_id,
            "verifyingContract": self.risk_router_address,
        }

        message = {
            "agentId": intent.agentId,
            "agentWallet": intent.agentWallet,
            "pair": intent.pair,
            "action": intent.action,
            "amountUsdScaled": intent.amountUsdScaled,
            "maxSlippageBps": intent.maxSlippageBps,
            "nonce": intent.nonce,
            "deadline": intent.deadline,
        }

        typed_data = {
            "types": TRADE_INTENT_TYPES,
            "primaryType": "TradeIntent",
            "domain": domain,
            "message": message,
        }

        signed = self.account.sign_typed_data(
            domain_data=domain,
            message_types={"TradeIntent": TRADE_INTENT_TYPES["TradeIntent"]},
            message_data=message,
        )
        signature = signed.signature.hex()
        if not signature.startswith("0x"):
            signature = "0x" + signature

        log.info(
            f"[eip712] TradeIntent signed | {action} {pair} ${amount_usd:.2f} "
            f"| nonce={nonce} | sig={signature[:18]}..."
        )
        return intent, signature

    def sign_checkpoint(
        self,
        agent_id: int,
        sequence_number: int,
        symbol: str,
        signal: str,
        strategy: str,
        regime: str,
        confidence: float,
        entry_price: float,
        reasoning: str,
    ) -> tuple[TradeCheckpoint, str, str]:
        """
        Sign a TradeCheckpoint for checkpoints.jsonl + ValidationRegistry.

        Returns:
            (TradeCheckpoint, hex_signature, reasoning_hash_hex)
        """
        from eth_abi.packed import encode_packed
        from Crypto.Hash import keccak as _keccak

        # keccak256 of the reasoning string
        keccak = _keccak.new(digest_bits=256)
        keccak.update(reasoning.encode("utf-8"))
        reasoning_hash = bytes.fromhex(keccak.hexdigest())

        checkpoint = TradeCheckpoint(
            agentId=agent_id,
            sequenceNumber=sequence_number,
            symbol=symbol,
            signal=signal.upper(),
            strategy=strategy,
            regime=regime,
            confidence=int(confidence * 100),
            entryPriceScaled=int(entry_price * 100),
            reasoningHash=reasoning_hash,
            timestamp=int(time.time()),
        )

        domain = {
            "name": "SentinelAgent",
            "version": "1",
            "chainId": self.chain_id,
        }

        message = {
            "agentId": checkpoint.agentId,
            "sequenceNumber": checkpoint.sequenceNumber,
            "symbol": checkpoint.symbol,
            "signal": checkpoint.signal,
            "strategy": checkpoint.strategy,
            "regime": checkpoint.regime,
            "confidence": checkpoint.confidence,
            "entryPriceScaled": checkpoint.entryPriceScaled,
            "reasoningHash": checkpoint.reasoningHash,
            "timestamp": checkpoint.timestamp,
        }

        signed = self.account.sign_typed_data(
            domain_data=domain,
            message_types={"TradeCheckpoint": TRADE_CHECKPOINT_TYPES["TradeCheckpoint"]},
            message_data=message,
        )
        signature = signed.signature.hex()
        if not signature.startswith("0x"):
            signature = "0x" + signature

        reasoning_hash_hex = "0x" + reasoning_hash.hex()

        log.info(
            f"[eip712] Checkpoint #{sequence_number} signed | {signal} {symbol} "
            f"@ ${entry_price:.2f} | {regime} | sig={signature[:18]}..."
        )
        return checkpoint, signature, reasoning_hash_hex

    def serialize_intent(self, intent: TradeIntent, signature: str) -> dict:
        """Serialize intent + sig for on-chain submission or logging."""
        return {
            "intent": {
                "agentId": intent.agentId,
                "agentWallet": intent.agentWallet,
                "pair": intent.pair,
                "action": intent.action,
                "amountUsdScaled": intent.amountUsdScaled,
                "maxSlippageBps": intent.maxSlippageBps,
                "nonce": intent.nonce,
                "deadline": intent.deadline,
            },
            "signature": signature,
        }

    def serialize_checkpoint(
        self,
        checkpoint: TradeCheckpoint,
        signature: str,
        reasoning_hash: str,
        reasoning: str,
        signal_data: Optional[dict] = None,
    ) -> dict:
        """Serialize checkpoint for checkpoints.jsonl."""
        return {
            "agentId": checkpoint.agentId,
            "sequenceNumber": checkpoint.sequenceNumber,
            "symbol": checkpoint.symbol,
            "signal": checkpoint.signal,
            "strategy": checkpoint.strategy,
            "regime": checkpoint.regime,
            "confidence": checkpoint.confidence / 100,
            "entryPriceScaled": checkpoint.entryPriceScaled,
            "entryPrice": checkpoint.entryPriceScaled / 100,
            "reasoning": reasoning,
            "reasoningHash": reasoning_hash,
            "timestamp": checkpoint.timestamp,
            "signature": signature,
            "signerWallet": self.agent_wallet,
            "chainId": self.chain_id,
            "signatureType": "eip712",
            "extraData": signal_data or {},
        }
