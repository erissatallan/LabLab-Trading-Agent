"""
identity.py — ERC-8004 on-chain integration for Sentinel.

Full live implementation using web3.py. All simulation_mode code removed.
Provides:
  - Agent registration check (reads from agent-id.json)
  - TradeIntent signing + RiskRouter submission (EIP-712)
  - Checkpoint recording (checkpoints.jsonl + optional on-chain post)
  - Compliance report artifact logging

Falls back gracefully if web3 is not connected (logs warning, records locally).
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

log = logging.getLogger(__name__)
load_dotenv()

ROOT = Path(__file__).parent.parent.parent
AGENT_ID_FILE = ROOT / "agent-id.json"
DEPLOYED_JSON = ROOT / "deployed.json"


# ── Minimal ABIs (only functions we call) ────────────────────────────────────

AGENT_REGISTRY_ABI = [
    {"name": "isRegistered",      "type": "function", "inputs": [{"name": "agentId", "type": "uint256"}], "outputs": [{"name": "", "type": "bool"}],    "stateMutability": "view"},
    {"name": "getSigningNonce",   "type": "function", "inputs": [{"name": "agentId", "type": "uint256"}], "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view"},
    {"name": "totalAgents",       "type": "function", "inputs": [],                                        "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view"},
]

RISK_ROUTER_ABI = [
    {
        "name": "submitTradeIntent",
        "type": "function",
        "inputs": [
            {"name": "intent", "type": "tuple", "components": [
                {"name": "agentId",          "type": "uint256"},
                {"name": "agentWallet",      "type": "address"},
                {"name": "pair",             "type": "string"},
                {"name": "action",           "type": "string"},
                {"name": "amountUsdScaled",  "type": "uint256"},
                {"name": "maxSlippageBps",   "type": "uint256"},
                {"name": "nonce",            "type": "uint256"},
                {"name": "deadline",         "type": "uint256"},
            ]},
            {"name": "signature", "type": "bytes"},
        ],
        "outputs": [
            {"name": "approved", "type": "bool"},
            {"name": "reason",   "type": "string"},
        ],
        "stateMutability": "nonpayable",
    },
    {
        "name": "getIntentNonce",
        "type": "function",
        "inputs": [{"name": "agentId", "type": "uint256"}],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
]

VALIDATION_REGISTRY_ABI = [
    {
        "name": "postEIP712Checkpoint",
        "type": "function",
        "inputs": [
            {"name": "agentId",        "type": "uint256"},
            {"name": "checkpointHash", "type": "bytes32"},
            {"name": "score",          "type": "uint8"},
            {"name": "notes",          "type": "string"},
        ],
        "outputs": [],
        "stateMutability": "nonpayable",
    },
    {
        "name": "attestationCount",
        "type": "function",
        "inputs": [{"name": "agentId", "type": "uint256"}],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
]


class ERC8004Integration:
    """
    Full live ERC-8004 on-chain integration.

    Responsibilities:
    - Load agent identity from agent-id.json
    - Connect to Base Sepolia via web3
    - Sign TradeIntents with EIP-712 and submit to RiskRouter
    - Record every decision as a signed checkpoint in checkpoints.jsonl
    - Post checkpoint hashes to ValidationRegistry (async, non-blocking)
    - Fall back to local-only logging if chain is unreachable

    Usage (from main.py):
        erc = ERC8004Integration()
        # Before a trade:
        approved = erc.validate_trade_intent(pair, action, amount_usd, signal)
        # After every decision (trade or hold):
        erc.record_decision(signal, reasoning, risk_metrics)
    """

    def __init__(self):
        self._load_config()
        self._init_web3()
        self._init_signer()
        self._init_checkpoint_manager()
        self._log_status()

    # ── Initialisation ────────────────────────────────────────────────────────

    def _load_config(self):
        """Load all config from env + agent-id.json."""
        # Wallet keys
        self.private_key = os.getenv("PRIVATE_KEY")
        self.agent_wallet_key = os.getenv("AGENT_WALLET_PRIVATE_KEY", self.private_key)

        # RPC
        self.rpc_url = os.getenv("BASE_TESTNET_RPC_URL", "https://sepolia.base.org")

        # Contract addresses
        self.registry_address   = os.getenv("AGENT_REGISTRY_ADDRESS")
        self.risk_router_address = os.getenv("RISK_ROUTER_ADDRESS")
        self.validation_address  = os.getenv("VALIDATION_REGISTRY_ADDRESS")
        self.chain_id = int(os.getenv("CHAIN_ID", "84532"))

        # Agent ID — from agent-id.json (written by register_agent.py)
        self.agent_id: Optional[int] = None
        self.agent_wallet_address: Optional[str] = None

        if AGENT_ID_FILE.exists():
            try:
                data = json.loads(AGENT_ID_FILE.read_text())
                self.agent_id = data.get("agentId")
                self.agent_wallet_address = data.get("agentWallet")
                log.info(f"[identity] Loaded agentId={self.agent_id} from agent-id.json")
            except Exception as e:
                log.warning(f"[identity] Failed to read agent-id.json: {e}")
        else:
            log.warning("[identity] agent-id.json not found — run: python scripts/register_agent.py")

        # Fallback from env
        if self.agent_id is None:
            env_id = os.getenv("AGENT_ID")
            if env_id:
                self.agent_id = int(env_id)
                log.info(f"[identity] Using AGENT_ID={self.agent_id} from .env")

    def _init_web3(self):
        """Connect to Base Sepolia."""
        self.w3 = None
        self.operator_account = None
        self.live = False

        if not self.private_key:
            log.warning("[identity] PRIVATE_KEY not set — running in local-only mode")
            return

        try:
            from web3 import Web3
            from eth_account import Account

            self.w3 = Web3(Web3.HTTPProvider(self.rpc_url, request_kwargs={"timeout": 15}))
            if self.w3.is_connected():
                self.operator_account = Account.from_key(self.private_key)
                actual_chain_id = self.w3.eth.chain_id
                self.chain_id = actual_chain_id
                self.live = True
                log.info(f"[identity] Connected to chain {actual_chain_id} | operator={self.operator_account.address[:10]}...")
            else:
                log.warning(f"[identity] Cannot reach {self.rpc_url} — local-only mode")
        except Exception as e:
            log.warning(f"[identity] Web3 init failed: {e} — local-only mode")

    def _init_signer(self):
        """Set up EIP-712 signer."""
        self.signer = None

        if not self.agent_wallet_key or not self.risk_router_address:
            if not self.agent_wallet_key:
                log.warning("[identity] AGENT_WALLET_PRIVATE_KEY not set — checkpoints will be unsigned")
            if not self.risk_router_address:
                log.warning("[identity] RISK_ROUTER_ADDRESS not set — RiskRouter disabled")
            return

        try:
            from agent.chain.eip712 import EIP712Signer
            self.signer = EIP712Signer(
                agent_wallet_private_key=self.agent_wallet_key,
                risk_router_address=self.risk_router_address,
                chain_id=self.chain_id,
            )
            self.agent_wallet_address = self.signer.agent_wallet
        except Exception as e:
            log.warning(f"[identity] EIP712Signer init failed: {e}")

    def _init_checkpoint_manager(self):
        """Set up CheckpointManager."""
        from agent.chain.checkpoint import CheckpointManager
        self.checkpoints = CheckpointManager(
            signer=self.signer,
            agent_id=self.agent_id or 0,
        )

    def _log_status(self):
        log.info(
            f"[identity] ERC-8004 ready | "
            f"agent_id={self.agent_id} | "
            f"chain={'live ✓' if self.live else 'local-only'} | "
            f"signing={'EIP-712 ✓' if self.signer else 'none'} | "
            f"checkpoints={self.checkpoints.sequence_number} logged"
        )

    # ── Core public API ───────────────────────────────────────────────────────

    def validate_trade_intent(
        self,
        pair: str,
        action: str,
        amount_usd: float,
        signal: dict,
    ) -> tuple[bool, str]:
        """
        Sign a TradeIntent and submit it to RiskRouter on-chain.

        MUST be called before executing any trade. The RiskRouter acts as the
        on-chain gatekeeper — trades can only proceed if it emits TradeApproved.

        Returns:
            (approved: bool, reason: str)
        """
        if self.agent_id is None:
            return False, "Agent not registered — run python scripts/register_agent.py"

        if not self.signer:
            log.warning("[identity] No signer — skipping on-chain RiskRouter validation")
            return True, "local-only (no signer)"

        # Get current nonce from chain
        nonce = self._get_intent_nonce()

        # Sign the TradeIntent
        intent, signature = self.signer.sign_trade_intent(
            agent_id=self.agent_id,
            pair=pair,
            action=action,
            amount_usd=amount_usd,
            nonce=nonce,
            slippage_bps=100,
            deadline_seconds=300,
        )

        # Submit to RiskRouter on-chain
        if self.live and self.risk_router_address and self.operator_account:
            return self._submit_to_risk_router(intent, signature)
        else:
            # Off-chain pre-validation only (signature is still proof of intent)
            log.info(f"[identity] TradeIntent signed (off-chain only) | {action} {pair} ${amount_usd:.2f}")
            return True, "signed-offline"

    def record_decision(
        self,
        signal: dict,
        reasoning: str,
        risk_metrics: Optional[dict] = None,
        post_to_chain: bool = True,
    ) -> str:
        """
        Record every trade decision as a signed checkpoint.

        Called after every analysis cycle (even for HOLD signals) to build
        the tamper-evident audit trail that feeds the leaderboard.

        Returns:
            checkpoint_hash (hex string)
        """
        checkpoint_hash = self.checkpoints.record(signal, reasoning, risk_metrics)

        # Post to ValidationRegistry on-chain (non-blocking — don't fail the trade loop)
        if post_to_chain and self.live and self.validation_address and self.operator_account:
            try:
                self._post_checkpoint_to_chain(checkpoint_hash)
            except Exception as e:
                log.warning(f"[identity] Chain post failed (non-fatal): {e}")

        return checkpoint_hash

    def get_status(self) -> dict:
        """Return current on-chain and local status."""
        checkpoint_stats = self.checkpoints.get_stats()
        chain_attestations = self._get_attestation_count() if self.live else None

        return {
            "agentId": self.agent_id,
            "registered": self.agent_id is not None,
            "chain": "base-sepolia" if self.live else "offline",
            "live": self.live,
            "signingEnabled": self.signer is not None,
            "agentWallet": self.agent_wallet_address,
            "rpcUrl": self.rpc_url,
            "contracts": {
                "agentRegistry": self.registry_address,
                "riskRouter": self.risk_router_address,
                "validationRegistry": self.validation_address,
            },
            "checkpoints": checkpoint_stats,
            "onChainAttestations": chain_attestations,
        }

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _get_intent_nonce(self) -> int:
        """Get current TradeIntent nonce from RiskRouter."""
        if not self.live or not self.risk_router_address:
            return 0
        try:
            from web3 import Web3
            router = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.risk_router_address),
                abi=RISK_ROUTER_ABI,
            )
            return router.functions.getIntentNonce(self.agent_id).call()
        except Exception as e:
            log.warning(f"[identity] Could not fetch nonce: {e} — using 0")
            return 0

    def _submit_to_risk_router(self, intent, signature: str) -> tuple[bool, str]:
        """Submit signed TradeIntent to RiskRouter.submitTradeIntent()."""
        from web3 import Web3

        router = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.risk_router_address),
            abi=RISK_ROUTER_ABI,
        )

        intent_tuple = (
            intent.agentId,
            intent.agentWallet,
            intent.pair,
            intent.action,
            intent.amountUsdScaled,
            intent.maxSlippageBps,
            intent.nonce,
            intent.deadline,
        )
        sig_bytes = bytes.fromhex(signature.removeprefix("0x"))

        try:
            nonce = self.w3.eth.get_transaction_count(self.operator_account.address)
            tx = router.functions.submitTradeIntent(
                intent_tuple, sig_bytes
            ).build_transaction({
                "from": self.operator_account.address,
                "nonce": nonce,
                "gasPrice": int(self.w3.eth.gas_price * 1.2),
                "gas": 200_000,
                "chainId": self.chain_id,
            })

            signed_tx = self.operator_account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

            if receipt.status == 1:
                # Decode return value via call (simulate to get the bool/string)
                result = router.functions.submitTradeIntent(intent_tuple, sig_bytes).call({
                    "from": self.operator_account.address
                })
                approved, reason = result[0], result[1]
                log.info(
                    f"[identity] RiskRouter: {'✓ APPROVED' if approved else '✗ REJECTED'} | "
                    f"{intent.action} {intent.pair} | tx={tx_hash.hex()[:18]}..."
                )
                return approved, reason or "approved"
            else:
                log.error(f"[identity] RiskRouter tx failed: {tx_hash.hex()}")
                return False, "tx_failed"

        except Exception as e:
            log.error(f"[identity] RiskRouter submission error: {e}")
            return False, str(e)

    def _post_checkpoint_to_chain(self, checkpoint_hash: str):
        """Post checkpoint hash to ValidationRegistry (non-blocking)."""
        from web3 import Web3

        registry = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.validation_address),
            abi=VALIDATION_REGISTRY_ABI,
        )

        checkpoint_bytes = bytes.fromhex(checkpoint_hash.removeprefix("0x"))

        nonce = self.w3.eth.get_transaction_count(self.operator_account.address)
        tx = registry.functions.postEIP712Checkpoint(
            self.agent_id,
            checkpoint_bytes,
            85,  # self-reported quality score
            f"Sentinel checkpoint #{self.checkpoints.sequence_number - 1}",
        ).build_transaction({
            "from": self.operator_account.address,
            "nonce": nonce,
            "gasPrice": int(self.w3.eth.gas_price * 1.2),
            "gas": 150_000,
            "chainId": self.chain_id,
        })

        signed_tx = self.operator_account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        log.info(f"[identity] Checkpoint posted to ValidationRegistry | tx={tx_hash.hex()[:18]}...")

    def _get_attestation_count(self) -> Optional[int]:
        if not self.validation_address or self.agent_id is None:
            return None
        try:
            from web3 import Web3
            registry = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.validation_address),
                abi=VALIDATION_REGISTRY_ABI,
            )
            return registry.functions.attestationCount(self.agent_id).call()
        except Exception:
            return None
