import logging
from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models import Wallet, Project, ProjectContract, Transaction
from backend.chains.rpc_pool import get_web3
from backend.chains.price_oracle import get_usd_price
from backend.telegram.alerts import create_and_send_alert
from backend.database import async_session

logger = logging.getLogger("airdrop.claims")

# Minimal ERC20/claim ABI fragments
_CLAIMABLE_ABI = [
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "claimable",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "earned",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "user", "type": "address"}],
        "name": "pendingReward",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

_CLAIM_EXEC_ABI = [
    {
        "inputs": [],
        "name": "claim",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "claimRewards",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

_CLAIMABLE_FNS = ["claimable", "earned", "pendingReward"]
_CLAIM_FNS = ["claim", "claimRewards"]


async def _check_claimable_amount(
    w3, contract_address: str, wallet_address: str
) -> Optional[int]:
    """
    Try multiple common claimable-view function names.
    Returns raw uint256 amount or None if not found / zero.
    """
    for fn_name in _CLAIMABLE_FNS:
        try:
            abi = [f for f in _CLAIMABLE_ABI if f["name"] == fn_name]
            contract = w3.eth.contract(
                address=w3.to_checksum_address(contract_address), abi=abi
            )
            fn = getattr(contract.functions, fn_name)
            amount = await fn(w3.to_checksum_address(wallet_address)).call()
            if amount and amount > 0:
                return int(amount)
        except Exception:
            continue
    return None


async def scan_claimable_airdrops(db: AsyncSession) -> List[dict]:
    """
    Scan all active wallets against all project claim contracts.
    Returns list of {wallet, project, contract, raw_amount, usd_estimate}.
    """
    wallets_result = await db.execute(
        select(Wallet).where(Wallet.status == "active", Wallet.is_gas_wallet == False)
    )
    wallets = wallets_result.scalars().all()

    projects_result = await db.execute(
        select(Project).where(Project.status == "active")
    )
    projects = projects_result.scalars().all()

    claimable = []

    for project in projects:
        contracts_result = await db.execute(
            select(ProjectContract).where(
                ProjectContract.project_id == project.id,
                ProjectContract.label.ilike("%claim%"),
            )
        )
        claim_contracts = contracts_result.scalars().all()

        if not claim_contracts:
            continue

        for contract in claim_contracts:
            try:
                # Build a minimal chain object for get_web3
                from backend.models import Chain
                chain_result = await db.execute(
                    select(Chain).where(Chain.id == contract.chain_id)
                )
                chain = chain_result.scalar_one_or_none()
                if not chain:
                    continue

                w3 = await get_web3(chain)

                for wallet in wallets:
                    try:
                        amount = await _check_claimable_amount(
                            w3, contract.address, wallet.address
                        )
                        if not amount:
                            continue

                        # Convert to USD estimate using price oracle
                        decimals = 18  # default; ideally from chain_tokens table
                        human_amount = amount / (10 ** decimals)
                        token_symbol = chain.gas_token_symbol
                        usd_price = await get_usd_price(token_symbol)
                        usd_est = human_amount * usd_price if usd_price else 0.0

                        claimable.append({
                            "wallet_id": wallet.id,
                            "wallet_address": wallet.address,
                            "project_id": project.id,
                            "project_name": project.name,
                            "contract_address": contract.address,
                            "chain_id": chain.id,
                            "chain_name": chain.name,
                            "raw_amount": amount,
                            "human_amount": round(human_amount, 6),
                            "token_symbol": token_symbol,
                            "usd_estimate": round(usd_est, 2),
                        })
                    except Exception as e:
                        logger.debug(
                            f"Claim check skip {wallet.address}/{contract.address}: {e}"
                        )
            except Exception as e:
                logger.error(f"Claim scan error project={project.id}: {e}")

    logger.info(f"Claim scan: {len(claimable)} claimable positions found")
    return claimable


async def auto_claim_if_below_threshold(
    wallet: Wallet,
    project: Project,
    contract_address: str,
    chain,
    raw_amount: int,
    usd_estimate: float,
    db: AsyncSession,
) -> bool:
    """
    Execute claim transaction if value is below auto_claim_threshold_usd.
    Notifies Telegram either way.
    """
    threshold = project.auto_claim_threshold_usd or 50.0

    if usd_estimate > threshold:
        await create_and_send_alert(
            type="claim_pending",
            severity="warning",
            message=(
                f"💰 *High-value claim ready!*\n"
                f"Project: {project.name}\n"
                f"Wallet: `{wallet.address[:10]}...`\n"
                f"Amount: ~${usd_estimate:.2f} USD\n"
                f"Use `/claim_trigger {wallet.id} {project.id}` to claim manually."
            ),
            wallet_id=wallet.id,
            project_id=project.id,
        )
        return False

    # Auto-claim
    try:
        from backend.tasks.claim_rewards import execute_claim
        success = await execute_claim(wallet, chain, contract_address, db)
        if success:
            await create_and_send_alert(
                type="claim_auto",
                severity="info",
                message=(
                    f"✅ *Auto-claimed!*\n"
                    f"Project: {project.name}\n"
                    f"Wallet: `{wallet.address[:10]}...`\n"
                    f"Value: ~${usd_estimate:.2f} USD"
                ),
                wallet_id=wallet.id,
                project_id=project.id,
            )
        return success
    except Exception as e:
        logger.error(f"Auto-claim failed: {e}")
        await create_and_send_alert(
            type="tx_failed",
            severity="warning",
            message=f"⚠️ Auto-claim failed for {project.name} / {wallet.address[:10]}...: {e}",
            wallet_id=wallet.id,
            project_id=project.id,
        )
        return False
