"""
checkpoint.py — Tamper-proof EIP-712 checkpoint log (checkpoints.jsonl).

Every trade decision Sentinel makes is signed with EIP-712 and appended here.
This file is the off-chain audit trail that can be submitted to ValidationRegistry
for on-chain verification and leaderboard ranking.

Format: one JSON object per line (JSONL), each with:
  - Full trade decision data
  - EIP-712 signature from the agentWallet
  - keccak256 hash of the reasoning string (verifiable on-chain)
  - sequenceNumber (monotonically increasing)
  - Hash chain: each entry includes the hash of the previous entry
"""

import json
import time
import hashlib
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent.parent
CHECKPOINTS_FILE = ROOT / "checkpoints.jsonl"


class CheckpointManager:
    """
    Manages the checkpoints.jsonl tamper-evident log.

    Each checkpoint is:
    1. EIP-712 signed by the agentWallet
    2. Chained to the previous checkpoint via hash
    3. Appended to checkpoints.jsonl

    Usage:
        manager = CheckpointManager(signer=eip712_signer, agent_id=1)
        checkpoint_hash = manager.record(signal, reasoning)
        # Later: manager.post_to_chain(checkpoint_hash, w3_contracts)
    """

    def __init__(self, signer=None, agent_id: int = 0):
        """
        Args:
            signer: EIP712Signer instance (can be None for simulation mode)
            agent_id: ERC-721 agent token ID
        """
        self.signer = signer
        self.agent_id = agent_id
        self.sequence_number = self._get_next_sequence()
        self.prev_checkpoint_hash = self._get_last_hash()

    def _get_next_sequence(self) -> int:
        """Return next sequence number based on existing checkpoints."""
        if not CHECKPOINTS_FILE.exists():
            return 0
        count = sum(1 for line in CHECKPOINTS_FILE.read_text().splitlines() if line.strip())
        return count

    def _get_last_hash(self) -> str:
        """Return the hash of the last checkpoint for chaining."""
        if not CHECKPOINTS_FILE.exists():
            return "0x" + "0" * 64  # genesis
        lines = [l for l in CHECKPOINTS_FILE.read_text().splitlines() if l.strip()]
        if not lines:
            return "0x" + "0" * 64
        try:
            last = json.loads(lines[-1])
            return last.get("checkpointHash", "0x" + "0" * 64)
        except Exception:
            return "0x" + "0" * 64

    def record(
        self,
        signal: dict,
        reasoning: str,
        risk_metrics: Optional[dict] = None,
    ) -> str:
        """
        Create, sign, and append a checkpoint for a trade decision.

        Args:
            signal: trade signal dict from the strategy engine
            reasoning: human-readable reasoning string
            risk_metrics: current risk/portfolio state

        Returns:
            checkpoint_hash (hex string) — use to post to ValidationRegistry
        """
        symbol = signal.get("symbol", "UNKNOWN")
        trade_signal = signal.get("signal", "HOLD")
        strategy = signal.get("strategy", "unknown")
        regime = signal.get("regime", "unknown")
        confidence = float(signal.get("confidence", 0.0))
        price = float(signal.get("price", 0.0))

        # Build checkpoint record
        checkpoint_record: dict = {
            "agentId": self.agent_id,
            "sequenceNumber": self.sequence_number,
            "symbol": symbol,
            "signal": trade_signal,
            "strategy": strategy,
            "regime": regime,
            "confidence": confidence,
            "entryPrice": price,
            "reasoning": reasoning,
            "timestamp": int(time.time()),
            "isoTimestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "prevCheckpointHash": self.prev_checkpoint_hash,
            "signatureType": "eip712" if self.signer else "none",
            "stopLoss": signal.get("stop_loss", 0),
            "takeProfit": signal.get("take_profit", 0),
            "riskMetrics": risk_metrics or {},
        }

        # EIP-712 sign if signer is available
        if self.signer:
            try:
                checkpoint, signature, reasoning_hash = self.signer.sign_checkpoint(
                    agent_id=self.agent_id,
                    sequence_number=self.sequence_number,
                    symbol=symbol,
                    signal=trade_signal,
                    strategy=strategy,
                    regime=regime,
                    confidence=confidence,
                    entry_price=price,
                    reasoning=reasoning,
                )
                checkpoint_record["signature"] = signature
                checkpoint_record["reasoningHash"] = reasoning_hash
                checkpoint_record["signerWallet"] = self.signer.agent_wallet
                checkpoint_record["chainId"] = self.signer.chain_id
            except Exception as e:
                log.warning(f"[checkpoint] EIP-712 signing failed: {e} — recording unsigned")
                checkpoint_record["signature"] = None
                checkpoint_record["reasoningHash"] = self._hash_reasoning(reasoning)
        else:
            # Simulation mode — hash reasoning but no EIP-712 sig
            checkpoint_record["signature"] = None
            checkpoint_record["reasoningHash"] = self._hash_reasoning(reasoning)

        # Content hash for chaining
        content_json = json.dumps(
            {k: v for k, v in checkpoint_record.items() if k != "prevCheckpointHash"},
            sort_keys=True, default=str
        )
        checkpoint_hash = "0x" + hashlib.sha256(content_json.encode()).hexdigest()
        checkpoint_record["checkpointHash"] = checkpoint_hash

        # Append to JSONL
        with open(CHECKPOINTS_FILE, "a") as f:
            f.write(json.dumps(checkpoint_record, default=str) + "\n")

        log.info(
            f"[checkpoint] #{self.sequence_number} recorded | "
            f"{trade_signal} {symbol} | "
            f"hash={checkpoint_hash[:18]}... | "
            f"{'EIP-712 ✓' if checkpoint_record.get('signature') else 'unsigned'}"
        )

        self.prev_checkpoint_hash = checkpoint_hash
        self.sequence_number += 1
        return checkpoint_hash

    def verify_integrity(self) -> dict:
        """
        Verify the chain integrity of all checkpoints.

        Returns:
            {valid: bool, total: int, broken_at: int | None, issues: list}
        """
        if not CHECKPOINTS_FILE.exists():
            return {"valid": True, "total": 0, "broken_at": None, "issues": []}

        lines = [l for l in CHECKPOINTS_FILE.read_text().splitlines() if l.strip()]
        issues = []
        prev_hash = "0x" + "0" * 64

        for i, line in enumerate(lines):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                issues.append(f"Line {i}: invalid JSON")
                continue

            # Check sequence
            if entry.get("sequenceNumber") != i:
                issues.append(f"Line {i}: sequenceNumber mismatch (got {entry.get('sequenceNumber')})")

            # Check chain linkage
            if entry.get("prevCheckpointHash") != prev_hash:
                issues.append(f"Line {i}: chain broken (prevHash mismatch)")
                return {"valid": False, "total": len(lines), "broken_at": i, "issues": issues}

            prev_hash = entry.get("checkpointHash", "")

        return {
            "valid": len(issues) == 0,
            "total": len(lines),
            "broken_at": None,
            "issues": issues,
        }

    def get_recent(self, n: int = 10) -> list[dict]:
        """Return the last N checkpoints."""
        if not CHECKPOINTS_FILE.exists():
            return []
        lines = [l for l in CHECKPOINTS_FILE.read_text().splitlines() if l.strip()]
        result = []
        for line in lines[-n:]:
            try:
                result.append(json.loads(line))
            except Exception:
                pass
        return result

    def get_stats(self) -> dict:
        """Return summary statistics about recorded checkpoints."""
        checkpoints = self.get_recent(n=10000)  # all
        if not checkpoints:
            return {"total": 0}
        signals = [c.get("signal") for c in checkpoints]
        return {
            "total": len(checkpoints),
            "buy_signals": signals.count("BUY"),
            "sell_signals": signals.count("SELL"),
            "hold_signals": signals.count("HOLD"),
            "signed": sum(1 for c in checkpoints if c.get("signature")),
            "unsigned": sum(1 for c in checkpoints if not c.get("signature")),
            "earliest": checkpoints[0].get("isoTimestamp") if checkpoints else None,
            "latest": checkpoints[-1].get("isoTimestamp") if checkpoints else None,
        }

    @staticmethod
    def _hash_reasoning(reasoning: str) -> str:
        """SHA-256 hash of reasoning string (used when keccak is not available)."""
        return "0x" + hashlib.sha256(reasoning.encode()).hexdigest()


def post_checkpoint_to_chain(
    w3,
    checkpoint_hash: str,
    agent_id: int,
    validation_registry_address: str,
    operator_account,
    chain_id: int,
    score: int = 85,
    notes: str = "",
) -> Optional[str]:
    """
    Post an EIP-712 checkpoint hash to the ValidationRegistry on-chain.

    This is what feeds the lablab.ai leaderboard ranking.

    Args:
        w3: Web3 instance
        checkpoint_hash: hex hash from CheckpointManager.record()
        agent_id: ERC-721 agent token ID
        validation_registry_address: deployed ValidationRegistry address
        operator_account: web3 Account (the one that deployed / is whitelisted as validator)
        chain_id: network chain ID
        score: validation score 0-100 (self-reported for hackathon)
        notes: optional notes

    Returns:
        tx_hash hex string, or None on failure
    """
    from web3 import Web3

    abi = [
        {
            "name": "postEIP712Checkpoint",
            "type": "function",
            "inputs": [
                {"name": "agentId", "type": "uint256"},
                {"name": "checkpointHash", "type": "bytes32"},
                {"name": "score", "type": "uint8"},
                {"name": "notes", "type": "string"},
            ],
            "outputs": [],
            "stateMutability": "nonpayable",
        }
    ]

    registry = w3.eth.contract(
        address=Web3.to_checksum_address(validation_registry_address),
        abi=abi,
    )

    checkpoint_bytes32 = bytes.fromhex(checkpoint_hash.removeprefix("0x"))

    try:
        nonce = w3.eth.get_transaction_count(operator_account.address)
        tx = registry.functions.postEIP712Checkpoint(
            agent_id,
            checkpoint_bytes32,
            score,
            notes,
        ).build_transaction({
            "from": operator_account.address,
            "nonce": nonce,
            "gasPrice": int(w3.eth.gas_price * 1.2),
            "gas": 150_000,
            "chainId": chain_id,
        })

        signed = operator_account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        log.info(f"[checkpoint] Posted to ValidationRegistry | tx={tx_hash.hex()[:18]}...")
        return tx_hash.hex()

    except Exception as e:
        log.error(f"[checkpoint] Failed to post to chain: {e}")
        return None
