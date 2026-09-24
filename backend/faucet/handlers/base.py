from abc import ABC, abstractmethod

class BaseFaucetHandler(ABC):
    @abstractmethod
    async def request(self, url: str, wallet_address: str, template: dict) -> dict:
        pass
