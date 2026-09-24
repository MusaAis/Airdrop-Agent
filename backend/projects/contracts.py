"""
CRUD operations for project contract addresses (per project per chain).
"""
import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models import ProjectContract

logger = logging.getLogger("airdrop.projects.contracts")


async def add_contract(
    db: AsyncSession,
    project_id: int,
    chain_id: int,
    label: str,
    address: str,
    abi_fragment: Optional[list] = None,
    verified: bool = False,
) -> ProjectContract:
    contract = ProjectContract(
        project_id=project_id,
        chain_id=chain_id,
        label=label,
        address=address,
        abi_fragment=abi_fragment,
        verified=verified,
    )
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    logger.info(f"Contract added: {label} @ {address} for project {project_id}")
    return contract


async def list_contracts(db: AsyncSession, project_id: int) -> List[ProjectContract]:
    result = await db.execute(
        select(ProjectContract).where(ProjectContract.project_id == project_id)
    )
    return result.scalars().all()


async def get_contract(db: AsyncSession, contract_id: int) -> Optional[ProjectContract]:
    return await db.get(ProjectContract, contract_id)


async def get_contract_by_label(
    db: AsyncSession, project_id: int, label: str
) -> Optional[ProjectContract]:
    result = await db.execute(
        select(ProjectContract).where(
            ProjectContract.project_id == project_id,
            ProjectContract.label == label,
        )
    )
    return result.scalar_one_or_none()


async def update_contract(
    db: AsyncSession,
    contract_id: int,
    address: Optional[str] = None,
    abi_fragment: Optional[list] = None,
    verified: Optional[bool] = None,
) -> Optional[ProjectContract]:
    contract = await db.get(ProjectContract, contract_id)
    if not contract:
        return None
    if address is not None:
        contract.address = address
    if abi_fragment is not None:
        contract.abi_fragment = abi_fragment
    if verified is not None:
        contract.verified = verified
    await db.commit()
    await db.refresh(contract)
    return contract


async def delete_contract(db: AsyncSession, contract_id: int) -> bool:
    contract = await db.get(ProjectContract, contract_id)
    if not contract:
        return False
    await db.delete(contract)
    await db.commit()
    return True

