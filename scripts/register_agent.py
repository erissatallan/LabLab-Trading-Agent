"""
register_agent.py — Register Sentinel on the AgentRegistry (ERC-721 mint).

Usage:
    python scripts/register_agent.py

Requires in .env:
    PRIVATE_KEY                  (operator wallet — owns the NFT, pays gas)
    AGENT_WALLET_PRIVATE_KEY     (hot wallet for signing — can be same key for hackathon)
    AGENT_REGISTRY_ADDRESS       (from scripts/deploy.py)
    RISK_ROUTER_ADDRESS          (from scripts/deploy.py)
    BASE_TESTNET_RPC_URL

After running, saves to agent-id.json and adds AGENT_ID to .env.
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

load_dotenv()

ROOT = Path(__file__).parent.parent


def load_abi(contract_name: str) -> list:
    """Load ABI from deployed.json or compile on-the-fly."""
    deployed_path = ROOT / "deployed.json"

    # Try to load from saved ABIs first
    abi_path = ROOT / "contracts" / "abis" / f"{contract_name}.json"
    if abi_path.exists():
        return json.loads(abi_path.read_text())

    # Fall back to compiling
    log.info(f"Compiling {contract_name} for ABI...")
    import solcx
    from pathlib import Path

    contracts_dir = ROOT / "contracts"
    sources = {f.name: {"content": f.read_text()} for f in contracts_dir.glob("*.sol")}

    compiled = solcx.compile_standard(
        {
            "language": "Solidity",
            "sources": sources,
            "settings": {
                "optimizer": {"enabled": True, "runs": 200},
                "outputSelection": {"*": {"*": ["abi"]}},
                "remappings": ["@openzeppelin/=node_modules/@openzeppelin/"],
            },
        },
        allow_paths=[str(ROOT), str(ROOT / "node_modules")],
        base_path=str(ROOT),
    )

    for src_name, contracts in compiled["contracts"].items():
        if contract_name in contracts:
            abi = contracts[contract_name]["abi"]
            # Cache the ABI
            abi_path.parent.mkdir(parents=True, exist_ok=True)
            abi_path.write_text(json.dumps(abi, indent=2))
            return abi

    raise ValueError(f"Contract {contract_name} not found in compiled output")


def build_agent_card(operator_address: str, agent_address: str) -> dict:
    """Build the Agent Card metadata JSON."""
    return {
        "name": "Sentinel",
        "description": "Trustless regime-adaptive trading agent. Detects trending vs sideways markets via ADX and switches between MACD momentum and Bollinger+RSI mean reversion strategies. All decisions logged via EIP-712 signed checkpoints on Base Sepolia.",
        "version": "1.0.0",
        "standard": "ERC-8004",
        "chain": "base-sepolia",
        "operatorWallet": operator_address,
        "agentWallet": agent_address,
        "capabilities": [
            "trading",
            "analysis",
            "eip712-signing",
            "regime-detection",
            "risk-management",
        ],
        "strategies": [
            "momentum_macd",
            "mean_reversion_bollinger_rsi",
            "regime_adaptive_ensemble",
        ],
        "riskParameters": {
            "maxPositionPct": 0.05,
            "maxDrawdownPct": 0.10,
            "dailyLossLimitPct": 0.03,
            "maxTradesPerHour": 10,
        },
        "tradingPairs": ["XBTUSD", "ETHUSD"],
        "dataSource": "kraken-cli",
        "repository": "https://github.com/allanerissat/sentinel-trading-agent",
        "registeredAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def update_env(updates: dict):
    env_path = ROOT / ".env"
    lines = env_path.read_text().splitlines() if env_path.exists() else []

    existing_keys = {}
    for i, line in enumerate(lines):
        if "=" in line and not line.strip().startswith("#"):
            key = line.split("=")[0].strip()
            existing_keys[key] = i

    for key, value in updates.items():
        line = f"{key}={value}"
        if key in existing_keys:
            lines[existing_keys[key]] = line
        else:
            lines.append(line)

    env_path.write_text("\n".join(lines) + "\n")


def main():
    # ── Config ──────────────────────────────────────────────────────────────
    private_key = os.getenv("PRIVATE_KEY")
    agent_wallet_key = os.getenv("AGENT_WALLET_PRIVATE_KEY", private_key)  # default same
    rpc_url = os.getenv("BASE_TESTNET_RPC_URL", "https://sepolia.base.org")
    registry_address = os.getenv("AGENT_REGISTRY_ADDRESS")
    risk_router_address = os.getenv("RISK_ROUTER_ADDRESS")

    if not private_key:
        log.error("❌ PRIVATE_KEY not set in .env")
        sys.exit(1)
    if not registry_address:
        log.error("❌ AGENT_REGISTRY_ADDRESS not set. Run: python scripts/deploy.py first")
        sys.exit(1)

    from web3 import Web3
    from eth_account import Account

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        log.error(f"❌ Cannot connect to {rpc_url}")
        sys.exit(1)

    operator = Account.from_key(private_key)
    agent_wallet = Account.from_key(agent_wallet_key)

    chain_id = w3.eth.chain_id
    balance = w3.from_wei(w3.eth.get_balance(operator.address), "ether")

    log.info("=" * 60)
    log.info("Sentinel Agent Registration")
    log.info("=" * 60)
    log.info(f"Network:        {rpc_url} (chain {chain_id})")
    log.info(f"Operator:       {operator.address}  (owns NFT)")
    log.info(f"Agent Wallet:   {agent_wallet.address}  (signs trades)")
    log.info(f"Balance:        {balance:.6f} ETH")
    log.info(f"AgentRegistry:  {registry_address}")
    log.info("=" * 60)

    # ── Build Agent Card ─────────────────────────────────────────────────────
    agent_card = build_agent_card(operator.address, agent_wallet.address)
    agent_card_json = json.dumps(agent_card, separators=(",", ":"))

    # Store Agent Card as local file and use data URI (IPFS would be better in prod)
    agent_card_path = ROOT / "agent-card.json"
    agent_card_path.write_text(json.dumps(agent_card, indent=2))
    log.info(f"Agent Card saved to: {agent_card_path}")

    # Use data URI for the token URI (works without IPFS for hackathon)
    import base64
    agent_uri = "data:application/json;base64," + base64.b64encode(agent_card_json.encode()).decode()

    # ── Load ABI and build contract ──────────────────────────────────────────
    # Minimal ABI for registration
    registry_abi = [
        {
            "name": "register",
            "type": "function",
            "inputs": [
                {"name": "agentWallet", "type": "address"},
                {"name": "name", "type": "string"},
                {"name": "description", "type": "string"},
                {"name": "capabilities", "type": "string[]"},
                {"name": "agentURI", "type": "string"},
            ],
            "outputs": [{"name": "agentId", "type": "uint256"}],
            "stateMutability": "nonpayable",
        },
        {
            "name": "walletToAgentId",
            "type": "function",
            "inputs": [{"name": "", "type": "address"}],
            "outputs": [{"name": "", "type": "uint256"}],
            "stateMutability": "view",
        },
        {
            "name": "isRegistered",
            "type": "function",
            "inputs": [{"name": "agentId", "type": "uint256"}],
            "outputs": [{"name": "", "type": "bool"}],
            "stateMutability": "view",
        },
        {
            "name": "totalAgents",
            "type": "function",
            "inputs": [],
            "outputs": [{"name": "", "type": "uint256"}],
            "stateMutability": "view",
        },
        {
            "name": "AgentRegistered",
            "type": "event",
            "inputs": [
                {"name": "agentId", "type": "uint256", "indexed": True},
                {"name": "operatorWallet", "type": "address", "indexed": True},
                {"name": "agentWallet", "type": "address", "indexed": True},
                {"name": "name", "type": "string", "indexed": False},
            ],
            "anonymous": False,
        },
    ]

    registry = w3.eth.contract(
        address=Web3.to_checksum_address(registry_address),
        abi=registry_abi,
    )

    # ── Check if already registered ──────────────────────────────────────────
    existing_id = registry.functions.walletToAgentId(agent_wallet.address).call()
    if existing_id != 0:
        log.info(f"⚠️  Agent wallet already registered with agentId={existing_id}")
        log.info("Skipping registration. Saving existing ID...")
        _save_agent_id(existing_id, registry_address, operator.address, agent_wallet.address)
        update_env({"AGENT_ID": str(existing_id)})
        return existing_id

    # ── Build and send registration transaction ───────────────────────────────
    log.info("\n[identity] Registering new agent on-chain (ERC-721 mint)...")

    nonce = w3.eth.get_transaction_count(operator.address)
    gas_price = int(w3.eth.gas_price * 1.2)

    tx = registry.functions.register(
        agent_wallet.address,
        "Sentinel",
        "Trustless regime-adaptive trading agent with EIP-712 signed checkpoints",
        ["trading", "analysis", "eip712-signing", "regime-detection", "risk-management"],
        agent_uri,
    ).build_transaction({
        "from": operator.address,
        "nonce": nonce,
        "gasPrice": gas_price,
        "chainId": chain_id,
    })

    try:
        tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.5)
    except Exception as e:
        log.warning(f"Gas estimation failed: {e}. Using fallback 2,000,000.")
        tx["gas"] = 2_000_000

    signed = operator.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    log.info(f"[identity] Registration tx: {tx_hash.hex()}")
    log.info("[identity] Waiting for confirmation...")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt.status != 1:
        log.error(f"❌ Registration transaction failed: {tx_hash.hex()}")
        sys.exit(1)

    # ── Extract agentId from logs ────────────────────────────────────────────
    logs = registry.events.AgentRegistered().process_receipt(receipt)
    agent_id = logs[0]["args"]["agentId"] if logs else None

    if agent_id is None:
        log.warning("Could not parse AgentRegistered event — reading from chain...")
        agent_id = registry.functions.walletToAgentId(agent_wallet.address).call()

    log.info(f"\n✅ Agent registered!")
    log.info(f"   agentId (ERC-721 token ID): {agent_id}")
    log.info(f"   Operator (NFT owner):       {operator.address}")
    log.info(f"   Agent wallet (hot signer):  {agent_wallet.address}")
    log.info(f"   Tx hash:                    {tx_hash.hex()}")
    log.info(f"   Basescan: https://sepolia.basescan.org/tx/{tx_hash.hex()}")

    # ── Set risk parameters on RiskRouter ────────────────────────────────────
    if risk_router_address:
        log.info(f"\\n[risk] Setting risk parameters on RiskRouter...")

        risk_abi = [
            {
                "name": "setRiskParams",
                "type": "function",
                "inputs": [
                    {"name": "agentId", "type": "uint256"},
                    {"name": "maxPositionUsdScaled", "type": "uint256"},
                    {"name": "maxDrawdownBps", "type": "uint256"},
                    {"name": "maxTradesPerHour", "type": "uint256"},
                ],
                "outputs": [],
                "stateMutability": "nonpayable",
            }
        ]

        risk_router = w3.eth.contract(
            address=Web3.to_checksum_address(risk_router_address),
            abi=risk_abi,
        )

        nonce = w3.eth.get_transaction_count(operator.address)
        tx = risk_router.functions.setRiskParams(
            agent_id,
            50000,   # maxPositionUsdScaled: $500 max per trade (500 * 100)
            500,     # maxDrawdownBps: 5%
            10,      # maxTradesPerHour: 10
        ).build_transaction({
            "from": operator.address,
            "nonce": nonce,
            "gasPrice": gas_price,
            "chainId": chain_id,
        })

        try:
            tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.5)
        except Exception:
            tx["gas"] = 500_000

        signed = operator.sign_transaction(tx)
        tx_hash2 = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt2 = w3.eth.wait_for_transaction_receipt(tx_hash2, timeout=120)

        if receipt2.status == 1:
            log.info(f"[risk] Risk params set: maxPosition=$500, maxDrawdown=5%, maxTrades/hr=10")
        else:
            log.warning(f"[risk] Risk params tx failed: {tx_hash2.hex()}")

    # ── Save everything ───────────────────────────────────────────────────────
    _save_agent_id(agent_id, registry_address, operator.address, agent_wallet.address)
    update_env({"AGENT_ID": str(agent_id)})

    log.info(f"\nAdd to .env (already done):")
    log.info(f"  AGENT_ID={agent_id}")
    log.info(f"\n✅ Next step: python -m agent.main --once")

    return agent_id


def _save_agent_id(agent_id, registry_address, operator, agent_wallet):
    data = {
        "agentId": agent_id,
        "agentRegistryAddress": registry_address,
        "operatorWallet": operator,
        "agentWallet": agent_wallet,
        "registeredAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "network": "base-sepolia",
    }
    path = Path(__file__).parent.parent / "agent-id.json"
    path.write_text(json.dumps(data, indent=2))
    log.info(f"[identity] Saved to agent-id.json")


if __name__ == "__main__":
    main()
