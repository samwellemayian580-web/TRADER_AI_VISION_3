"""HFM MT5 account profiles for TRADER AI VISION 3."""

ACCOUNTS = {
    "DEMO": {
        "broker": "HFM",
        "server": "HFMarketsKE-Demo2",
        "symbol": "XAUUSD",
    },
    "LIVE": {
        "broker": "HFM",
        "server": "HFMarketsKE-Live2",
        "symbol": "XAUUSD",
    },
}

DEFAULT_ACCOUNT = "DEMO"


def get_account(mode=DEFAULT_ACCOUNT):
    mode = str(mode).upper()

    if mode not in ACCOUNTS:
        raise ValueError("Account must be DEMO or LIVE")

    return {
        **ACCOUNTS[mode],
        "mode": mode,
    }


def available_accounts():
    return list(ACCOUNTS.keys())
