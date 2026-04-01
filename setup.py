#!/usr/bin/env python3
"""
setup.py — One-command setup for Sentinel.

Installs Python deps, OpenZeppelin contracts, and checks the environment.

Usage:
    python setup.py
"""

import subprocess
import sys
import os
from pathlib import Path

ROOT = Path(__file__).parent

BOLD  = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED   = "\033[31m"
RESET = "\033[0m"

def step(msg): print(f"\n{BOLD}▶ {msg}{RESET}")
def ok(msg):   print(f"  {GREEN}✓ {msg}{RESET}")
def warn(msg): print(f"  {YELLOW}⚠ {msg}{RESET}")
def fail(msg): print(f"  {RED}✗ {msg}{RESET}")


def run(cmd, cwd=None, check=True):
    result = subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True, text=True)
    if check and result.returncode != 0:
        fail(f"Command failed: {' '.join(cmd)}")
        print(result.stderr)
        sys.exit(1)
    return result


def check_python():
    step("Checking Python version")
    v = sys.version_info
    if v.major < 3 or v.minor < 11:
        fail(f"Python 3.11+ required, got {v.major}.{v.minor}")
        sys.exit(1)
    ok(f"Python {v.major}.{v.minor}.{v.micro}")


def install_python_deps():
    step("Installing Python dependencies")
    run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"])
    ok("Python packages installed")

    # Install solc
    step("Installing Solidity compiler (solc 0.8.24)")
    try:
        import solcx
        solcx.install_solc("0.8.24")
        solcx.set_solc_version("0.8.24")
        ok("solc 0.8.24 ready")
    except Exception as e:
        warn(f"solc install failed: {e} — deploy.py may not work")


def install_node_deps():
    step("Installing OpenZeppelin contracts (npm)")
    node_check = subprocess.run(["node", "--version"], capture_output=True, text=True)
    if node_check.returncode != 0:
        warn("Node.js not found — install from https://nodejs.org (needed for OpenZeppelin)")
        return

    npm_check = subprocess.run(["npm", "--version"], capture_output=True, text=True)
    if npm_check.returncode != 0:
        warn("npm not found")
        return

    run(["npm", "install", "--silent"])
    ok("OpenZeppelin contracts installed in node_modules/")


def check_env():
    step("Checking .env configuration")
    env_path = ROOT / ".env"
    if not env_path.exists():
        fail(".env file not found")
        return

    from dotenv import dotenv_values
    env = dotenv_values(str(env_path))

    checks = {
        "PRIVATE_KEY":               ("Operator wallet private key", True),
        "AGENT_WALLET_PRIVATE_KEY":  ("Agent hot wallet private key", False),
        "BASE_TESTNET_RPC_URL":      ("Base Sepolia RPC URL", True),
        "PRISM_API_KEY":             ("PRISM API key", False),
        "AGENT_REGISTRY_ADDRESS":    ("AgentRegistry contract (run deploy.py)", False),
        "AGENT_ID":                  ("Agent ID (run register_agent.py)", False),
    }

    all_critical_ok = True
    for key, (desc, required) in checks.items():
        val = env.get(key, "")
        if val and not val.startswith("<"):
            ok(f"{key} — set")
        elif required:
            fail(f"{key} — MISSING ({desc})")
            all_critical_ok = False
        else:
            warn(f"{key} — not set ({desc})")

    return all_critical_ok


def check_agent_id():
    step("Checking agent registration")
    agent_id_path = ROOT / "agent-id.json"
    deployed_path = ROOT / "deployed.json"

    if deployed_path.exists():
        import json
        d = json.loads(deployed_path.read_text())
        ok(f"Contracts deployed | AgentRegistry={d.get('AGENT_REGISTRY_ADDRESS', '?')[:10]}...")
    else:
        warn("Contracts not deployed — run: python scripts/deploy.py")

    if agent_id_path.exists():
        import json
        d = json.loads(agent_id_path.read_text())
        ok(f"Agent registered | agentId={d.get('agentId')} | wallet={d.get('agentWallet', '')[:10]}...")
    else:
        warn("Agent not registered — run: python scripts/register_agent.py")


def print_next_steps(env_ok: bool):
    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}Setup complete! Next steps:{RESET}")
    print(f"{'=' * 60}")

    if not env_ok:
        print(f"""
{RED}1. Add your private key to .env:{RESET}
   PRIVATE_KEY=0x<your_metamask_private_key>
   AGENT_WALLET_PRIVATE_KEY=0x<same_or_separate_hot_wallet>

   Export from MetaMask: Account Details → Show Private Key
""")

    print(f"""
{YELLOW}2. Get Base Sepolia ETH (for gas):{RESET}
   https://www.coinbase.com/faucets/base-ethereum-sepolia-faucet
   https://www.alchemy.com/faucets/base-sepolia

{YELLOW}3. Deploy contracts:{RESET}
   python scripts/deploy.py

{YELLOW}4. Register agent on-chain (mints ERC-721 NFT):{RESET}
   python scripts/register_agent.py

{GREEN}5. Run Sentinel:{RESET}
   python -m agent.main --once        # single iteration test
   python -m agent.main               # continuous trading loop
   python -m agent.main --status      # check chain status

{GREEN}6. View dashboard:{RESET}
   python dashboard/app.py
""")


def main():
    print(f"{BOLD}")
    print("  ███████╗███████╗███╗   ██╗████████╗██╗███╗   ██╗███████╗██╗     ")
    print("  ██╔════╝██╔════╝████╗  ██║╚══██╔══╝██║████╗  ██║██╔════╝██║     ")
    print("  ███████╗█████╗  ██╔██╗ ██║   ██║   ██║██╔██╗ ██║█████╗  ██║     ")
    print("  ╚════██║██╔══╝  ██║╚██╗██║   ██║   ██║██║╚██╗██║██╔══╝  ██║     ")
    print("  ███████║███████╗██║ ╚████║   ██║   ██║██║ ╚████║███████╗███████╗")
    print("  ╚══════╝╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝╚═╝  ╚═══╝╚══════╝╚══════╝")
    print(f"  ERC-8004 Regime-Adaptive Trading Agent — Setup{RESET}\n")

    check_python()
    install_python_deps()
    install_node_deps()
    env_ok = check_env()
    check_agent_id()
    print_next_steps(env_ok)


if __name__ == "__main__":
    main()
