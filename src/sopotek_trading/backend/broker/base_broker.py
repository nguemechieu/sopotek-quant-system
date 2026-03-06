class BaseBroker:

    async def connect(self):
        raise NotImplementedError

    async def fetch_symbols(self):
        raise NotImplementedError

    async def fetch_balance(self):
        raise NotImplementedError

    async def place_order( self,
                           symbol: str,
                           side: str,
                           order_type: str,
                           amount: float,
                           price: float | None = None,
                           stop_loss: float | None = None,
                           take_profit: float | None = None,
                           slippage: float | None = None,):
        raise NotImplementedError

    async def cancel_order(self, order_id, symbol):
        raise NotImplementedError

    async def fetch_positions(self):
        raise NotImplementedError

    async def close(self):
        raise NotImplementedError