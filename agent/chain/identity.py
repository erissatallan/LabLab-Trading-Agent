"""
ERC-8004 on-chain integration for Sentinel.

Handles:
- Agent identity registration (ERC-721 NFT mint)
- Validation artifact submission (trade intents, risk checks, compliance reports)
- Reputation querying

Uses Web3.py to interact with contracts on Base L2.
"""

import json
import hashlib
import logging
import os
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()


@dataclass
class AgentCard:
    """ERC-8004 Agent Card metadata (stored off-chain, referenced by tokenURI)."""
    name: str = "Sentinel"
    description: str = "Trustless regime-adaptive trading agent"
    version: str = "0.1.0"
    capabilities: list = None
    strategies: list = None
    risk_parameters: dict = None
    endpoints: dict = None

    def __post_init__(self):
        self.capabilities = self.capabilities or [
            "spot_trading",
            "regime_detection",
            "risk_management",
            "compliance_reporting",
        ]
        self.strategies = self.strategies or [
            "momentum_macd",
            "mean_reversion_bollinger_rsi",
            "regime_adaptive_ensemble",
        ]
        self.risk_parameters = self.risk_parameters or {
            "max_position_pct": 0.05,
            "max_drawdown_pct": 0.10,
            "daily_loss_limit_pct": 0.03,
            "max_positions": 5,
        }
        self.endpoints = self.endpoints or {}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": self.capabilities,
            "strategies": self.strategies,
            "risk_parameters": self.risk_parameters,
            "endpoints": self.endpoints,
            "standard": "ERC-8004",
            "chain": "base",
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class ERC8004Integration:
    """
    Python-side ERC-8004 integration layer.

    For the hackathon, we implement a simplified version that:
    1. Generates Agent Card metadata
    2. Hashes validation artifacts
    3. Prepares transactions for on-chain submission
    4. Can operate in "simulation mode" without actual on-chain calls

    For production: would use Web3.py to interact with deployed contracts on Base.
    """

    def __init__(
        self,
        wallet_address: str = None,
        rpc_url: str = None,
        simulation_mode: bool = True,
    ):
        self.wallet_address = wallet_address or os.getenv("WALLET_ADDRESS", "")
        self.rpc_url = rpc_url or os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
        self.simulation_mode = simulation_mode

        self.agent_card = AgentCard()
        self.agent_id: Optional[int] = None
        self.artifacts: list[dict] = []

        self.web3 = None
        if not simulation_mode:
            self._init_web3()

        logger.info(
            f"ERC-8004 integration initialized | "
            f"Wallet: {self.wallet_address[:10]}...{self.wallet_address[-6:]} | "
            f"Mode: {'simulation' if simulation_mode else 'live'}"
        )

    def _init_web3(self):
        """Initialize Web3 connection to Base."""
        try:
            from web3 import Web3
            self.web3 = Web3(Web3.HTTPProvider(self.rpc_url))
            if self.web3.is_connected():
                logger.info(f"Connected to Base at {self.rpc_url}")
                chain_id = self.web3.eth.chain_id
                logger.info(f"Chain ID: {chain_id}")
            else:
                logger.warning("Failed to connect to Base RPC")
                self.simulation_mode = True
        except ImportError:
            logger.warning("web3 not installed, falling back to simulation mode")
            self.simulation_mode = True

    def register_agent(self) -> dict:
        """
        Register the Sentinel agent on the ERC-8004 Identity Registry.
        Returns registration details.
        """
        agent_card_json = self.agent_card.to_json()
        agent_card_hash = self._hash_content(agent_card_json)

        registration = {
            "action": "register_agent",
            "timestamp": datetime.utcnow().isoformat(),
            "wallet": self.wallet_address,
            "agent_card": self.agent_card.to_dict(),
            "agent_card_hash": agent_card_hash,
            "status": "simulated" if self.simulation_mode else "pending",
        }

        if self.simulation_mode:
            self.agent_id = 1  # Simulated agent ID
            registration["agent_id"] = self.agent_id
            registration["status"] = "registered"
            logger.info(f"Agent registered (simulated): ID={self.agent_id}")
        else:
            # TODO: Actual contract interaction via Web3.py
            # tx = self.contract.functions.register(agent_uri).build_transaction(...)
            pass

        return registration

    def submit_trade_intent(self, trade_signal: dict) -> dict:
        """
        Submit a trade intent as an ERC-8004 validation artifact.
        Called BEFORE executing a trade — proves the agent's decision process.
        """
        artifact = {
            "type": "trade_intent",
            "agent_id": self.agent_id,
            "timestamp": datetime.utcnow().isoformat(),
            "content": {
                "symbol": trade_signal.get("symbol", ""),
                "signal": trade_signal.get("signal", ""),
                "strategy": trade_signal.get("strategy", ""),
                "confidence": trade_signal.get("confidence", 0),
                "entry_price": trade_signal.get("price", 0),
                "stop_loss": trade_signal.get("stop_loss", 0),
                "take_profit": trade_signal.get("take_profit", 0),
                "regime": trade_signal.get("regime", ""),
                "reasoning": trade_signal.get("reasoning", ""),
            },
        }

        artifact_json = json.dumps(artifact["content"], sort_keys=True)
        artifact["content_hash"] = self._hash_content(artifact_json)

        if self.simulation_mode:
            artifact["artifact_id"] = len(self.artifacts) + 1
            artifact["status"] = "submitted"
        else:
            # TODO: Write to chain
            pass

        self.artifacts.append(artifact)
        logger.info(f"Trade intent artifact submitted: hash={artifact['content_hash'][:16]}...")
        return artifact

    def submit_risk_check(self, risk_metrics: dict) -> dict:
        """
        Submit a risk check as an ERC-8004 validation artifact.
        Proves the agent respects its stated risk parameters.
        """
        artifact = {
            "type": "risk_check",
            "agent_id": self.agent_id,
            "timestamp": datetime.utcnow().isoformat(),
            "content": {
                "equity": risk_metrics.get("equity", 0),
                "peak_equity": risk_metrics.get("peak_equity", 0),
                "drawdown": risk_metrics.get("drawdown", 0),
                "daily_pnl": risk_metrics.get("daily_pnl", 0),
                "open_positions": risk_metrics.get("open_positions", 0),
                "status": risk_metrics.get("status", ""),
                "within_limits": risk_metrics.get("status") in ("normal", "caution"),
            },
        }

        artifact_json = json.dumps(artifact["content"], sort_keys=True)
        artifact["content_hash"] = self._hash_content(artifact_json)

        if self.simulation_mode:
            artifact["artifact_id"] = len(self.artifacts) + 1
            artifact["status"] = "submitted"

        self.artifacts.append(artifact)
        logger.info(f"Risk check artifact submitted: hash={artifact['content_hash'][:16]}...")
        return artifact

    def submit_compliance_report(self, compliance_report: dict) -> dict:
        """
        Submit a full compliance report as a validation artifact.
        Called periodically to prove ongoing compliance.
        """
        artifact = {
            "type": "compliance_report",
            "agent_id": self.agent_id,
            "timestamp": datetime.utcnow().isoformat(),
            "content": compliance_report,
        }

        artifact_json = json.dumps(artifact["content"], sort_keys=True, default=str)
        artifact["content_hash"] = self._hash_content(artifact_json)

        if self.simulation_mode:
            artifact["artifact_id"] = len(self.artifacts) + 1
            artifact["status"] = "submitted"

        self.artifacts.append(artifact)
        logger.info(f"Compliance report artifact submitted: hash={artifact['content_hash'][:16]}...")
        return artifact

    def get_on_chain_status(self) -> dict:
        """Get summary of on-chain presence."""
        return {
            "registered": self.agent_id is not None,
            "agent_id": self.agent_id,
            "wallet": self.wallet_address,
            "chain": "base",
            "mode": "simulation" if self.simulation_mode else "live",
            "total_artifacts": len(self.artifacts),
            "artifact_breakdown": {
                "trade_intents": len([a for a in self.artifacts if a["type"] == "trade_intent"]),
                "risk_checks": len([a for a in self.artifacts if a["type"] == "risk_check"]),
                "compliance_reports": len([a for a in self.artifacts if a["type"] == "compliance_report"]),
            },
            "recent_artifacts": self.artifacts[-5:] if self.artifacts else [],
        }

    @staticmethod
    def _hash_content(content: str) -> str:
        """Generate keccak256-style hash of content."""
        return "0x" + hashlib.sha256(content.encode()).hexdigest()
