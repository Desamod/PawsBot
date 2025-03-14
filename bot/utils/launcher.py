import asyncio
import argparse
from random import randint
from typing import Any
from better_proxy import Proxy

from bot.config import settings
from bot.utils import logger
from bot.core.tapper import run_tapper
from bot.core.registrator import register_sessions
from bot.utils.accounts import Accounts
from bot.core.TgManager.tg_manager import SessionManager
from bot.core.WalletManager.WalletManager import generate_wallets, get_not_connected_wallets
from bot.core.WalletManager.SolanaManager import get_solana_not_connected_wallets, generate_solana_wallets


start_text = """

██████╗░░█████╗░░██╗░░░░░░░██╗░██████╗██████╗░░█████╗░████████╗
██╔══██╗██╔══██╗░██║░░██╗░░██║██╔════╝██╔══██╗██╔══██╗╚══██╔══╝
██████╔╝███████║░╚██╗████╗██╔╝╚█████╗░██████╦╝██║░░██║░░░██║░░░
██╔═══╝░██╔══██║░░████╔═████║░░╚═══██╗██╔══██╗██║░░██║░░░██║░░░
██║░░░░░██║░░██║░░╚██╔╝░╚██╔╝░██████╔╝██████╦╝╚█████╔╝░░░██║░░░
╚═╝░░░░░╚═╝░░╚═╝░░░╚═╝░░░╚═╝░░╚═════╝░╚═════╝░░╚════╝░░░░╚═╝░░░
                                                     by Desamod                                                              
Select an action:

    1. Run bot
    2. Create session (Pyrogram)
    3. Generate TON wallets
    4. Generate Solana wallets
"""


def get_proxy(raw_proxy: str) -> Proxy:
    return Proxy.from_str(proxy=raw_proxy).as_url if raw_proxy else None


async def process() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--action", type=int, help="Action to perform")
    action = parser.parse_args().action

    if not action:
        print(start_text)

        while True:
            action = input("> ")

            if not action.isdigit():
                logger.warning("Action must be number")
            elif action not in ["1", "2", "3", "4"]:
                logger.warning("Action must be 1, 2, 3 or 4")
            else:
                action = int(action)
                break

    if action == 4:
        count = input("Enter the number of wallets (Solana) to generate: ")
        try:
            count = int(count)
            generate_solana_wallets(count)
            logger.success('Wallets successfully generated, check solana_wallets.txt file')
        except ValueError:
            logger.warning("Please enter a valid number.")
            return
    elif action == 3:
        count = input("Enter the number of wallets (Ton) to generate: ")
        try:
            count = int(count)
            generate_wallets(count)
            logger.success('Wallets successfully generated, check wallets.txt file')
        except ValueError:
            logger.warning("Please enter a valid number.")
            return
    elif action == 2:
        await register_sessions()
    elif action == 1:
        accounts = await Accounts().get_accounts()
        await run_tasks(accounts=accounts)


async def run_tasks(accounts: [Any, Any, list]):
    tasks = []
    manager = SessionManager(api_id=settings.API_ID,
                             api_hash=settings.API_HASH,
                             peer='Free_PWS_Bot',
                             short_name='login',
                             start_param=settings.REF_ID,
                             check_first_run=True)

    if settings.CONNECT_TON_WALLET:
        valid_wallets = get_not_connected_wallets()
        logger.info(f'Found <e>{len(valid_wallets)}</e> not connected wallet/s (Ton)')
    if settings.CONNECT_SOLANA_WALLET:
        valid_solana_wallets = get_solana_not_connected_wallets()
        logger.info(f'Found <e>{len(valid_solana_wallets)}</e> not connected wallet/s (Solana)')
    for account in accounts:
        session_name, user_agent, raw_proxy = account.values()
        tg_session = await manager.get_tg_session(session_name=session_name, proxy=raw_proxy)
        proxy = get_proxy(raw_proxy=raw_proxy)
        tasks.append(asyncio.create_task(run_tapper(tg_session=tg_session, user_agent=user_agent, proxy=proxy)))
        await asyncio.sleep(delay=randint(settings.START_DELAY[0], settings.START_DELAY[1]))

    await asyncio.gather(*tasks)
