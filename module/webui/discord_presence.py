import asyncio
import time

from pypresence import AioPresence

RPC: AioPresence | None = None


async def run():
    assert RPC is not None
    await RPC.connect()
    await RPC.update(state="Alas is playing Azurlane", start=int(time.time()), large_image="alas")


def init_discord_rpc():
    global RPC, _rpc_task
    RPC = AioPresence("929437173764223057")
    _rpc_task = asyncio.create_task(run())


def close_discord_rpc():
    # Local alias: pyright does not narrow module globals across statements,
    # and sock_writer is nullable until connect() completes.
    rpc = RPC
    if rpc is not None and rpc.sock_writer is not None:
        rpc.send_data(2, {"v": 1, "client_id": rpc.client_id})
        rpc.sock_writer.close()
