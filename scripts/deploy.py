"""
deploy.py — Compile and deploy all 5 ERC-8004 contracts to Base Sepolia.

Usage:
    python scripts/deploy.py

Requires in .env:
    PRIVATE_KEY=0x...            (wallet private key — this wallet pays gas and owns NFT)
    BASE_TESTNET_RPC_URL=...     (Base Sepolia RPC, e.g. https://sepolia.base.org)

After running, adds to .env:
    AGENT_REGISTRY_ADDRESS
    HACKATHON_VAULT_ADDRESS
    RISK_ROUTER_ADDRESS
    REPUTATION_REGISTRY_ADDRESS
    VALIDATION_REGISTRY_ADDRESS
    CHAIN_ID
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
CONTRACTS_DIR = ROOT / "contracts"


def check_dependencies():
    """Verify required packages are installed."""
    missing = []
    for pkg in ["web3", "solcx", "eth_account"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        log.error(f"Missing packages: {missing}")
        log.error("Run: pip install web3 py-solc-x eth-account")
        sys.exit(1)


def install_solc():
    """Install and select the Solidity compiler version."""
    import solcx
    version = "0.8.25"
    installed = solcx.get_installed_solc_versions()
    if not any(str(v) == version for v in installed):
        log.info(f"Installing solc {version}...")
        solcx.install_solc(version)
    solcx.set_solc_version(version)
    log.info(f"✓ solc {version} ready")


def compile_contracts():
    """Compile all contracts returning {ContractName: {abi, bytecode}}."""
    import solcx

    log.info("Compiling contracts...")

    sources = {}
    for sol_file in CONTRACTS_DIR.glob("*.sol"):
        sources[sol_file.name] = {"content": sol_file.read_text()}

    # Map OpenZeppelin imports to installed package path
    import subprocess, site
    site_pkgs = site.getsitepackages()
    oz_path = None
    for sp in site_pkgs:
        candidate = Path(sp) / "openzeppelin" / "contracts"
        if candidate.exists():
            oz_path = str(Path(sp))
            break
    # Alternative: pip install openzeppelin-contracts-python or use remappings
    # We'll use solcx with remapping via --base-path and installed npm package alternative

    compiled = solcx.compile_standard(
        {
            "language": "Solidity",
            "sources": sources,
            "settings": {
                "optimizer": {"enabled": True, "runs": 200},
                "viaIR": True,
                "outputSelection": {
                    "*": {"*": ["abi", "evm.bytecode"]}
                },
                "remappings": [
                    "@openzeppelin/=node_modules/@openzeppelin/"
                ],
            },
        },
        allow_paths=[str(ROOT), str(ROOT / "node_modules")],
        base_path=str(ROOT),
    )

    results = {}
    for src_name, contracts in compiled["contracts"].items():
        for contract_name, data in contracts.items():
            abi = data["abi"]
            bytecode = data["evm"]["bytecode"]["object"]
            if bytecode:  # skip interfaces
                results[contract_name] = {"abi": abi, "bytecode": bytecode}
                log.info(f"  ✓ {contract_name}")

    return results


def deploy_contract(w3, account, abi, bytecode, nonce, *args):
    """Deploy a single contract and return its address."""
    from eth_account import Account

    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    gas_price = w3.eth.gas_price

    tx = contract.constructor(*args).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gasPrice": int(gas_price * 1.2),  # 20% bump for faster inclusion
    })

    # Estimate gas
    try:
        tx["gas"] = w3.eth.estimate_gas(tx)
    except Exception:
        tx["gas"] = 3_000_000  # fallback

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    log.info(f"  ↳ tx: {tx_hash.hex()} (waiting...)")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt.status != 1:
        raise RuntimeError(f"Deployment failed: {tx_hash.hex()}")

    return receipt.contractAddress, tx_hash.hex()


def update_env(updates: dict):
    """Append/update key=value pairs in .env file."""
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
    log.info(f"  ✓ .env updated with {list(updates.keys())}")


def save_deployed_json(addresses: dict, chain_id: int):
    """Save deployed addresses to deployed.json."""
    deployed = {
        "chainId": chain_id,
        "network": "base-sepolia",
        "deployed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **addresses,
    }
    path = ROOT / "deployed.json"
    path.write_text(json.dumps(deployed, indent=2))
    log.info(f"  ✓ Addresses saved to deployed.json")
    return deployed


def main():
    check_dependencies()

    private_key = os.getenv("PRIVATE_KEY")
    rpc_url = os.getenv("BASE_TESTNET_RPC_URL", "https://sepolia.base.org")

    if not private_key:
        log.error("❌ PRIVATE_KEY not found in .env")
        log.error("Add: PRIVATE_KEY=0x<your_private_key>")
        sys.exit(1)

    from web3 import Web3
    from eth_account import Account

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        log.error(f"❌ Cannot connect to {rpc_url}")
        sys.exit(1)

    account = Account.from_key(private_key)
    chain_id = w3.eth.chain_id
    balance_eth = w3.from_wei(w3.eth.get_balance(account.address), "ether")

    log.info("=" * 60)
    log.info("Sentinel Contract Deployment")
    log.info("=" * 60)
    log.info(f"Network:  {rpc_url}")
    log.info(f"Chain ID: {chain_id}")
    log.info(f"Deployer: {account.address}")
    log.info(f"Balance:  {balance_eth:.6f} ETH")
    log.info("=" * 60)

    if float(balance_eth) < 0.005:
        log.warning(f"⚠️  Low balance ({balance_eth:.6f} ETH) — may not cover gas")
        log.warning("Get Base Sepolia ETH from: https://www.coinbase.com/faucets/base-ethereum-sepolia-faucet")

    install_solc()
    compiled = compile_contracts()

    addresses = {}

    # 1. AgentRegistry
    log.info("\n1/5 Deploying AgentRegistry (ERC-721)...")
    current_nonce = w3.eth.get_transaction_count(account.address, 'pending')
    
    addr, tx = deploy_contract(
        w3, account,
        compiled["AgentRegistry"]["abi"],
        compiled["AgentRegistry"]["bytecode"],
        current_nonce
    )
    addresses["AGENT_REGISTRY_ADDRESS"] = addr
    log.info(f"  ✓ AgentRegistry: {addr}")
    current_nonce += 1

    # 2. HackathonVault
    log.info("\n2/5 Deploying HackathonVault...")
    addr, tx = deploy_contract(
        w3, account,
        compiled["HackathonVault"]["abi"],
        compiled["HackathonVault"]["bytecode"],
        current_nonce
    )
    addresses["HACKATHON_VAULT_ADDRESS"] = addr
    log.info(f"  ✓ HackathonVault: {addr}")
    current_nonce += 1

    # 3. RiskRouter (needs AgentRegistry address)
    log.info("\n3/5 Deploying RiskRouter...")
    addr, tx = deploy_contract(
        w3, account,
        compiled["RiskRouter"]["abi"],
        compiled["RiskRouter"]["bytecode"],
        current_nonce,
        addresses["AGENT_REGISTRY_ADDRESS"]
    )
    addresses["RISK_ROUTER_ADDRESS"] = addr
    log.info(f"  ✓ RiskRouter: {addr}")
    current_nonce += 1

    # 4. ReputationRegistry (needs AgentRegistry address)
    log.info("\n4/5 Deploying ReputationRegistry...")
    addr, tx = deploy_contract(
        w3, account,
        compiled["ReputationRegistry"]["abi"],
        compiled["ReputationRegistry"]["bytecode"],
        current_nonce,
        addresses["AGENT_REGISTRY_ADDRESS"]
    )
    addresses["REPUTATION_REGISTRY_ADDRESS"] = addr
    log.info(f"  ✓ ReputationRegistry: {addr}")
    current_nonce += 1

    # 5. ValidationRegistry (needs AgentRegistry address, open=True so we can self-post)
    log.info("\n5/5 Deploying ValidationRegistry...")
    addr, tx = deploy_contract(
        w3, account,
        compiled["ValidationRegistry"]["abi"],
        compiled["ValidationRegistry"]["bytecode"],
        current_nonce,
        addresses["AGENT_REGISTRY_ADDRESS"],
        True  # openValidation = True so the agent can post its own checkpoints
    )
    addresses["VALIDATION_REGISTRY_ADDRESS"] = addr
    log.info(f"  ✓ ValidationRegistry: {addr}")

    # Save everything
    addresses["CHAIN_ID"] = str(chain_id)
    log.info("\n" + "=" * 60)
    log.info("All contracts deployed!")
    log.info("=" * 60)

    update_env(addresses)
    save_deployed_json(addresses, chain_id)

    log.info("\n── Add these to your .env (already done automatically) ──")
    for key, val in addresses.items():
        log.info(f"  {key}={val}")

    log.info("\n✅ Next step: python scripts/register_agent.py")


if __name__ == "__main__":
    main()
