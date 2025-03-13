from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    API_ID: int
    API_HASH: str

    SLEEP_TIME: list[int] = [7200, 10800]
    START_DELAY: list[int] = [5, 25]
    AUTO_TASK: bool = False
    JOIN_TG_CHANNELS: bool = False
    REF_ID: str = 'idqtVYZG'
    DISABLED_TASKS: list[str] = ['boost', 'emoji']
    SIMPLE_TASKS: list[str] = ['twitter', 'linked', 'paragraph']
    WEB_TASKS: list[str] = ["67814ddc6806dce25e57fe20", "67717bfb067c823d800e5a14"]
    VERIFY_WALLETS: bool = False
    CONNECT_TON_WALLET: bool = False
    DISCONNECT_TON_WALLET: bool = False
    CONNECT_SOLANA_WALLET: bool = False
    DISCONNECT_SOLANA_WALLET: bool = False
    CLEAR_TG_NAME: bool = False
    CHECK_ELIGIBILITY: bool = True
    SOLVE_CAPTCHA: bool = False
    CONNECT_EXCHANGE: bool = False
    CAPTCHA_API_KEY: str = ""


settings = Settings()
