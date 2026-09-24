import asyncio
from decimal import Decimal
from web3 import AsyncWeb3
from backend.models import Chain, ChainToken
from backend.chains.rpc_pool import get_web3
from backend.chains.price_oracle import get_usd_price
import logging

logger = logging.getLogger("airdrop.balance")

async def check_native_balance(w3: AsyncWeb3, address: str) -> Decimal:
    balance_wei = await w3.eth.get_balance(address)
    return Decimal(balance_wei) / Decimal(10**18)

async def check_erc20_balance_raw(w3: AsyncWeb3, contract_address: str, address: str) -> int:
    abi = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]
    contract = w3.eth.contract(address=contract_address, abi=abi)
    return await contract.functions.balanceOf(address).call()

async def get_gas_token_balance(chain: Chain, address: str) -> Decimal:
    w3 = await get_web3(chain)
    if chain.gas_token_is_native:
        return await check_native_balance(w3, address)
    else:
        raw = await check_erc20_balance_raw(w3, chain.gas_token_contract, address)
        return Decimal(raw) / Decimal(10 ** chain.gas_token_decimals)


async def refresh_wallet_balances(db, wallet, chains: list) -> list:
    """
    Check the gas token AND every registered ERC20 token (chain_tokens) for a
    wallet across the given chains, and upsert the results into WalletBalance
    with a USD value. Previously WalletBalance existed as a model with no
    code path that ever wrote to it — there was no way to see which wallets
    actually have funds without manually querying a chain explorer per wallet
    per chain.

    Returns the list of WalletBalance rows that were written (for the route
    to return immediately without a second query).
    """
    from sqlalchemy import select
    from backend.models import WalletBalance, ChainToken
    from datetime import datetime, timezone

    written = []
    for chain in chains:
        if not chain.enabled:
            continue
        try:
            w3 = await get_web3(chain)
        except Exception as e:
            logger.warning(f"Could not connect to {chain.name} for balance refresh: {e}")
            continue

        # 1. Gas token (native or ERC20)
        try:
            gas_balance = await get_gas_token_balance(chain, wallet.address)
            gas_coingecko_id = chain.gas_token_symbol.lower()
            usd = None
            try:
                price = await get_usd_price(gas_coingecko_id)
                if price is not None:
                    usd = float(gas_balance) * price
            except Exception:
                pass
            written.append(await _upsert_balance(
                db, wallet.id, chain.id, chain.gas_token_symbol, float(gas_balance), usd
            ))
        except Exception as e:
            logger.warning(f"Gas balance check failed for wallet={wallet.id} chain={chain.id}: {e}")

        # 2. Every other registered token on this chain
        result = await db.execute(select(ChainToken).where(ChainToken.chain_id == chain.id))
        for token in result.scalars().all():
            if token.is_gas_token:
                continue  # already covered above
            try:
                raw = await check_erc20_balance_raw(w3, token.contract_address, wallet.address)
                bal = Decimal(raw) / Decimal(10 ** token.decimals)
                usd = None
                try:
                    cg_id = token.coingecko_id or token.symbol.lower()
                    price = await get_usd_price(cg_id)
                    if price is not None:
                        usd = float(bal) * price
                except Exception:
                    pass
                written.append(await _upsert_balance(
                    db, wallet.id, chain.id, token.symbol, float(bal), usd
                ))
            except Exception as e:
                logger.debug(f"Token balance check failed for {token.symbol} on chain={chain.id}: {e}")

    await db.commit()
    return written


async def _upsert_balance(db, wallet_id: int, chain_id: int, symbol: str, balance: float, usd_value):
    from sqlalchemy import select
    from backend.models import WalletBalance
    from datetime import datetime, timezone

    result = await db.execute(
        select(WalletBalance).where(
            WalletBalance.wallet_id == wallet_id,
            WalletBalance.chain_id == chain_id,
            WalletBalance.token_symbol == symbol,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        row.balance = balance
        row.usd_value = usd_value
        row.last_updated = datetime.now(timezone.utc)
    else:
        row = WalletBalance(
            wallet_id=wallet_id, chain_id=chain_id, token_symbol=symbol,
            balance=balance, usd_value=usd_value, last_updated=datetime.now(timezone.utc),
        )
        db.add(row)
    return row

# No more double division
