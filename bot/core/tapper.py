import asyncio
import sys
from time import time

import cloudscraper
from aiocfscrape import CloudflareScraper
from aiohttp_proxy import ProxyConnector
from better_proxy import Proxy
from bot.config import settings

from bot.utils import logger
from bot.exceptions import InvalidSession
from .agents import get_sec_ch_ua, is_latest_tg_version
from .headers import headers

from random import randint

from ..utils.api_checker import is_valid_endpoints
from ..utils.tg_manager.TGSession import TGSession
from bot.core.WalletManager.WalletManager import get_valid_wallet, set_wallet
from bot.core.WalletManager.SolanaManager import get_solana_valid_wallet, set_solana_wallet


class Tapper:
    def __init__(self, tg_session: TGSession):
        self.tg_session = tg_session
        self.session_name = tg_session.session_name
        self.start_param = ''
        self.name = ''
        self.wallet = ''
        self.solana_wallet = ''
        self.paws_id = ''
        self.is_grinch = None

    async def send_plausible_event(self,http_client: cloudscraper.CloudScraper, web_data: str, event_name='pageview'):
        try:
            payload = {
                "d": "app.paws.community",
                "n": event_name,
                "r": None,
                "u": web_data
            }
            response = http_client.post("https://plausible.io/api/event", json=payload)
            if response.status_code == 202:
                logger.success(
                    f'{self.session_name} | Sent plausible game event: <fg #008080>{event_name}</fg #008080>')
                return True
            else:
                return False
        except:
            return False

    async def login(self, http_client: cloudscraper.CloudScraper, tg_web_data: str, retry=0):
        try:
            payload = {'data': tg_web_data}
            if self.tg_session.start_param:
                payload['referralCode'] = self.tg_session.start_param

            response = http_client.post("https://api.paws.community/v1/user/auth", json=payload,
                                        timeout=60)

            response.raise_for_status()
            response_json = response.json()
            auth_token = None
            if response_json.get('success', False):
                auth_token = response_json.get('data', None)
            return auth_token

        except Exception as error:
            if retry < 3:
                logger.warning(f"{self.session_name} | Can't logging | Retry attempt: {retry}")
                await asyncio.sleep(delay=randint(5, 10))
                return await self.login(http_client, tg_web_data=tg_web_data, retry=retry + 1)

            logger.error(f"{self.session_name} | Unknown error when logging: {error}")
            await asyncio.sleep(delay=randint(3, 7))

    async def check_proxy(self, http_client: cloudscraper.CloudScraper, proxy: str) -> None:
        try:
            response = http_client.get(url='https://ipinfo.io/ip', timeout=20)
            ip = response.text
            logger.info(f"{self.session_name} | Proxy IP: {ip}")
        except Exception as error:
            logger.error(f"{self.session_name} | Proxy: {proxy} | Error: {error}")

    async def get_all_tasks(self, http_client: cloudscraper.CloudScraper, retry=0):
        try:
            response = http_client.get(f"https://api.paws.community/v1/quests/list")
            response.raise_for_status()
            return response.json().get('data', [])
        except Exception as error:
            if retry < 3:
                logger.warning(f"{self.session_name} | Can't getting tasks | Retry attempt: {retry}")
                await asyncio.sleep(delay=randint(5, 10))
                return await self.get_all_tasks(http_client, retry=retry + 1)

            logger.error(f"{self.session_name} | Unknown error when getting tasks: {error}")
            await asyncio.sleep(delay=3)

    async def processing_tasks(self, http_client: cloudscraper.CloudScraper):
        try:
            tasks = await self.get_all_tasks(http_client)
            if tasks:
                tasks = sorted(tasks, key=lambda t: t.get('sort', 999))
                for task in tasks:
                    progress = task['progress']
                    if not progress['claimed'] and task['code'] not in settings.DISABLED_TASKS:
                        result = True if (progress['current'] == progress['total'] and
                                          progress['status'] == "claimable") else None
                        if progress['current'] < progress['total'] or progress['status'] != "claimable":
                            is_partner = task.get('partner', False)
                            if task['code'] == 'telegram':
                                if task['flag'] == 0:
                                    logger.info(f"{self.session_name} | Performing TG task <lc>{task['title']}</lc>")
                                else:
                                    if not settings.JOIN_TG_CHANNELS:
                                        continue

                                    url = task['data']
                                    logger.info(f"{self.session_name} | Performing TG subscription to <lc>{url}</lc>")
                                    await self.tg_session.join_tg_channel(url)
                            elif task['code'] == 'invite':
                                counter = task['counter']
                                referrals = await self.get_referrals(http_client)
                                if counter > len(referrals):
                                    continue
                            elif (task['code'] in settings.SIMPLE_TASKS or is_partner) and task['flag'] == 0:
                                logger.info(f"{self.session_name} | Performing <lc>{task['title']}</lc> task")
                            elif task['code'] == 'daily' or task['code'] == 'custom':
                                end_time = task.get('availableUntil', 0)
                                curr_time = time() * 1000
                                if end_time < curr_time:
                                    continue
                                if task['flag'] == 1:
                                    if task['type'] == 'social':
                                        if progress['current'] != progress['total'] or progress['status'] != 'start':
                                            continue
                                    if task['type'] == 'ton':
                                        if progress['status'] != 'check':
                                            continue
                                logger.info(f"{self.session_name} | Performing <lc>{task['title']}</lc> task")

                            elif task['code'] == 'wallet':
                                if self.wallet is not None and len(self.wallet) > 0:
                                    logger.info(
                                        f"{self.session_name} | Performing wallet task: <lc>{task['title']}</lc>")
                                else:
                                    continue

                            elif task['code'] == 'custom1' and task['type'] == 'soll-wallet':
                                end_time = task.get('availableUntil', 0)
                                curr_time = time() * 1000
                                if (self.solana_wallet is not None and len(self.solana_wallet) > 0
                                        and end_time > curr_time):
                                    logger.info(f"{self.session_name} | "
                                                f"Performing Solana wallet task: <lc>{task['title']}</lc>")
                                else:
                                    continue

                            elif task['code'] == 'emojiName':
                                logger.info(f"{self.session_name} | Performing <lc>{task['title']}</lc> task")
                                if '🐾' not in self.tg_session.name:
                                    nickname = f'{self.tg_session.name}🐾'
                                    await self.tg_session.change_tg_nickname(name=nickname)
                                    continue
                            else:
                                logger.info(
                                    f"{self.session_name} | Unrecognized task: <lc>{task['title']}</lc>")
                                continue

                            result = await self.verify_task(http_client, task['_id'])

                        if result is not None:
                            await asyncio.sleep(delay=randint(5, 10))
                            is_claimed, amount = await self.claim_task_reward(http_client, task['_id'])
                            if is_claimed:
                                rewards = task['rewards'][0]
                                amount = rewards['amount'] if amount is None else amount
                                logger.success(f"{self.session_name} | Task <lc>{task['title']}</lc> completed! | "
                                               f"Reward: <e>+{amount}</e> PAWS")
                            else:
                                logger.info(f"{self.session_name} | "
                                            f"Rewards for task <lc>{task['title']}</lc> not claimed")
                        else:
                            logger.info(f"{self.session_name} | Task <lc>{task['title']}</lc> not completed")

                        await asyncio.sleep(delay=randint(5, 10))

        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error when processing tasks: {error}")
            await asyncio.sleep(delay=3)

    async def verify_task(self, http_client: cloudscraper.CloudScraper, task_id: str, retry=0):
        try:
            payload = {'questId': task_id}
            response = http_client.post(f'https://api.paws.community/v1/quests/completed',
                                        json=payload, timeout=60)
            response.raise_for_status()
            response_json = response.json()
            status = response_json.get('success', False) and response_json.get('data', False)
            return status

        except Exception as e:
            if retry < 3:
                logger.warning(f"{self.session_name} | Can't verify task | Retry attempt: {retry}")
                await asyncio.sleep(delay=randint(5, 10))
                return await self.verify_task(http_client, task_id, retry=retry + 1)

            logger.error(f"{self.session_name} | Unknown error while verifying task <lc>{task_id}</lc> | Error: {e}")
            await asyncio.sleep(delay=3)

    async def claim_task_reward(self, http_client: cloudscraper.CloudScraper, task_id: str):
        try:
            payload = {'questId': task_id}
            response = http_client.post(f'https://api.paws.community/v1/quests/claim',
                                        json=payload, timeout=60)
            response.raise_for_status()
            response_json = response.json()
            status = response_json.get('success', False) or response_json.get('completed', False)
            reward_data = response_json.get('data', None)
            amount = None
            if reward_data:
                amount = reward_data.get('amount', None)
            return status, amount

        except Exception as e:
            logger.error(
                f"{self.session_name} | Unknown error while claim reward for task <lc>{task_id}</lc> | Error: {e}")
            await asyncio.sleep(delay=3)
            return None, None

    async def get_referrals(self, http_client: cloudscraper.CloudScraper):
        try:
            response = http_client.get(f'https://api.paws.community/v1/referral/my',
                                       timeout=60)
            response.raise_for_status()
            response_json = response.json()
            return response_json.get('data', [])

        except Exception as e:
            logger.error(f"{self.session_name} | Unknown error while getting referrals | Error: {e}")
            await asyncio.sleep(delay=3)

    async def check_wallet_status(self, scraper: cloudscraper.CloudScraper, wallet_type: str,
                                  is_connected: bool, need_to_connect: bool, need_to_disconnect: bool):
        if not is_connected and need_to_connect:
            await asyncio.sleep(randint(5, 10))
            valid_wallet = get_valid_wallet() if wallet_type == 'Ton' else get_solana_valid_wallet()
            if valid_wallet is not None:
                wallet_address = valid_wallet['address']
                logger.info(f'{self.session_name} | Found valid {wallet_type} wallet: <y>{wallet_address}</y>')
                result = None
                if wallet_type == 'Ton':
                    result = await set_wallet(self.session_name, scraper, wallet_address)
                elif wallet_type == 'Solana':
                    result = await set_solana_wallet(self.session_name, scraper, wallet_address, self.paws_id)

                if result is not None:
                    logger.success(f'{self.session_name} | '
                                   f'{wallet_type} wallet: <y>{wallet_address}</y> successfully connected')
                    if wallet_type == 'Ton':
                        self.wallet = wallet_address
                    elif wallet_type == 'Solana':
                        self.solana_wallet = wallet_address
            else:
                logger.warning(f'{self.session_name} | A valid {wallet_type} wallet was not found. '
                               f'Try adding new wallets manually or generating them using command 3')

        elif is_connected and need_to_disconnect:
            await asyncio.sleep(randint(5, 10))
            result = None
            if wallet_type == 'Ton':
                result = await set_wallet(self.session_name, scraper, self.wallet, connect=False)
            elif wallet_type == 'Solana':
                result = await set_solana_wallet(self.session_name, scraper, self.solana_wallet,
                                                 self.paws_id, connect=False)
            if result is not None:
                logger.success(f'{self.session_name} | '
                               f'{wallet_type} wallet: <y>{self.wallet}</y> successfully disconnected')
                if wallet_type == 'Ton':
                    self.wallet = None
                elif wallet_type == 'Solana':
                    self.solana_wallet = None

    async def get_user_info(self, http_client: cloudscraper.CloudScraper, retry=0):
        try:
            response = http_client.get('https://api.paws.community/v1/user')
            response.raise_for_status()
            response_json = response.json()
            if response_json.get('success', False):
                user_data = response_json.get('data')
                return user_data
            else:
                raise Exception

        except Exception as e:
            if retry < 3:
                logger.warning(f"{self.session_name} | Can't get user info | Retry attempt: {retry}")
                await asyncio.sleep(delay=randint(5, 10))
                return await self.get_user_info(http_client, retry=retry + 1)

            logger.error(f"{self.session_name} | Unknown error while getting user info | Error: {e}")
            await asyncio.sleep(delay=3)

    async def set_grinch_event(self, http_client: cloudscraper.CloudScraper):
        try:
            response = http_client.post('https://api.paws.community/v1/user/grinch', json={})
            response.raise_for_status()
            response_json = response.json()
            if response_json.get('success', False):
                logger.success(f'{self.session_name} | Grinch event successfully started')
                self.is_grinch = False
            else:
                raise Exception

        except Exception as e:
            logger.error(f"{self.session_name} | Unknown error while setting Grinch event | Error: {e}")
            await asyncio.sleep(delay=3)

    async def processing_grinch_tasks(self, http_client: cloudscraper.CloudScraper):
        try:
            logger.info(f'{self.session_name} | Processing Grinch tasks')
            response = http_client.get('https://api.paws.community/v1/quests/list?type=christmas')
            response.raise_for_status()
            response_json = response.json()
            tasks = response_json['data']
            tasks = sorted(tasks, key=lambda t: t.get('sort', 999), reverse=True)
            for task in tasks:
                await asyncio.sleep(randint(2, 5))
                progress = task['progress']
                if not progress['claimed']:
                    result = await self.verify_task(http_client, task['_id'])
                    if result is not None:
                        await asyncio.sleep(delay=randint(2, 7))
                        is_claimed, amount = await self.claim_task_reward(http_client, task['_id'])
                        if is_claimed:
                            reward = f" | Reward: <e>+{amount}</e> PAWS" if amount is not None else ''
                            logger.success(f"{self.session_name} | Grinch task <lc>{task['title']}</lc> completed!"
                                           f"{reward}")
                        else:
                            logger.info(f"{self.session_name} | "
                                        f"Rewards for task <lc>{task['title']}</lc> not claimed")
                            break

        except Exception as e:
            logger.error(f"{self.session_name} | Unknown error while processing Grinch tasks | Error: {e}")
            await asyncio.sleep(delay=3)

    async def run(self, user_agent: str, proxy: str | None) -> None:
        access_token_created_time = 0
        proxy_conn = ProxyConnector().from_url(proxy) if proxy else None
        headers["User-Agent"] = user_agent
        headers['Sec-Ch-Ua'] = get_sec_ch_ua(user_agent)

        http_client = CloudflareScraper(headers=headers, connector=proxy_conn, trust_env=True,
                                        auto_decompress=False)
        scraper = cloudscraper.create_scraper()
        if proxy:
            proxies = {
                'http': proxy,
                'https': proxy,
                'socks5': proxy
            }
            scraper.proxies.update(proxies)
            await self.check_proxy(http_client=scraper, proxy=proxy)

        token_live_time = randint(3500, 3600)
        scraper.headers = http_client.headers.copy()
        while True:
            try:
                sleep_time = randint(settings.SLEEP_TIME[0], settings.SLEEP_TIME[1])
                if time() - access_token_created_time >= token_live_time:
                    tg_web_data = await self.tg_session.get_tg_web_data()
                    if tg_web_data is None:
                        continue

                    if not is_valid_endpoints():
                        logger.warning("Detected api change! Stopped the bot for safety | "
                                       "Contact me for update: <lc>https://t.me/DesQwertys</lc>")
                        sys.exit()
                    else:
                        logger.info(f"{self.session_name} | Antidetect: endpoints successfully checked")

                    #if await self.send_plausible_event(http_client=scraper, web_data="https://app.paws.community/") is False:
                    #   await asyncio.sleep(randint(5, 10))
                    #   continue
                    auth_data = await self.login(http_client=scraper, tg_web_data=tg_web_data)
                    auth_token = auth_data[0]
                    if auth_token is None:
                        token_live_time = 0
                        await asyncio.sleep(randint(100, 180))
                        continue

                    access_token_created_time = time()
                    token_live_time = randint(3500, 3600)

                    http_client.headers['Authorization'] = f'Bearer {auth_token}'
                    scraper.headers = http_client.headers.copy()
                    user_info = auth_data[1]
                    self.paws_id = user_info['_id']
                    balance = user_info['gameData']['balance']
                    wallet = user_info['userData'].get('wallet', None)
                    solana_wallet = user_info['userData'].get('solanaWallet', None)
                    self.is_grinch = user_info.get('grinchRemoved', None)
                    self.wallet = wallet
                    self.solana_wallet = solana_wallet
                    is_wallet_connected = wallet is not None and len(wallet) > 0
                    is_solana_wallet_connected = solana_wallet is not None and len(solana_wallet) > 0
                    wallet_status = f"Ton Wallet: <y>{wallet}</y>" if is_wallet_connected \
                        else 'Ton wallet not connected'
                    solana_wallet_status = f"Solana wallet: <y>{solana_wallet}</y>" if is_solana_wallet_connected \
                        else 'Solana wallet not connected'
                    logger.info(f"{self.session_name} | Balance: <e>{balance}</e> PAWS")
                    logger.info(f"{self.session_name} | {wallet_status}")
                    logger.info(f"{self.session_name} | {solana_wallet_status}")

                    if self.is_grinch is None:
                        await asyncio.sleep(2)
                        await self.set_grinch_event(http_client=scraper)

                    await self.check_wallet_status(scraper=scraper, wallet_type='Ton',
                                                   is_connected=is_wallet_connected,
                                                   need_to_connect=settings.CONNECT_TON_WALLET,
                                                   need_to_disconnect=settings.DISCONNECT_TON_WALLET)
                    await self.check_wallet_status(scraper=scraper, wallet_type='Solana',
                                                   is_connected=is_solana_wallet_connected,
                                                   need_to_connect=settings.CONNECT_SOLANA_WALLET,
                                                   need_to_disconnect=settings.DISCONNECT_SOLANA_WALLET)

                    if settings.AUTO_TASK:
                        await asyncio.sleep(delay=randint(5, 10))
                        await self.processing_tasks(http_client=scraper)
                        logger.info(f"{self.session_name} | All available tasks completed")

                    if not self.is_grinch:
                        await asyncio.sleep(delay=randint(5, 10))
                        await self.processing_grinch_tasks(http_client=scraper)

                if settings.CLEAR_TG_NAME and '🐾' in self.tg_session.name:
                    logger.info(f"{self.session_name} | Removing 🐾 from name..")
                    nickname = self.tg_session.name.replace('🐾', '')
                    await self.tg_session.change_tg_nickname(name=nickname)

                logger.info(f"{self.session_name} | Sleep <y>{round(sleep_time / 60, 1)}</y> min")
                await asyncio.sleep(delay=sleep_time)

            except InvalidSession as error:
                raise error

            except Exception as error:
                logger.error(f"{self.session_name} | Unknown error: {error}")
                await asyncio.sleep(delay=randint(60, 120))

            except KeyboardInterrupt:
                logger.warning("<r>Bot stopped by user...</r>")
            finally:
                if scraper is not None:
                    await http_client.close()
                    scraper.close()


async def run_tapper(tg_session: TGSession, user_agent: str, proxy: str | None):
    try:
        await Tapper(tg_session=tg_session).run(user_agent=user_agent, proxy=proxy)
    except InvalidSession:
        logger.error(f"{tg_session.session_name} | Invalid Session")
