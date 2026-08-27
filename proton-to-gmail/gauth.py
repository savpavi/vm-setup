"""Ortak Gmail API kimlik dogrulama katmani.

authorize.py ve migrate.py bunu kullanir. token.json burada okunur/yenilenir.
"""
import sys
import threading
from pathlib import Path

WORKDIR = Path(__file__).resolve().parent
ENV_FILE = WORKDIR / ".env"
TOKEN_FILE = WORKDIR / "token.json"

DEFAULT_SCOPE = "https://mail.google.com/"


def load_env():
    if not ENV_FILE.exists():
        sys.exit(f"HATA: {ENV_FILE} yok. Once setup-wizard.sh calistir.")
    env = {}
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def save_token(creds):
    TOKEN_FILE.write_text(creds.to_json())
    TOKEN_FILE.chmod(0o600)


def get_credentials(env, scopes, allow_interactive=True):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = None
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), scopes)
        except Exception as e:
            print(f"  uyari: token.json okunamadi ({e})")
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_token(creds)
            return creds
        except Exception as e:
            print(f"  uyari: token yenilenemedi ({e})")

    if not allow_interactive:
        sys.exit("HATA: gecerli token yok. Once authorize.py calistir.")

    from google_auth_oauthlib.flow import InstalledAppFlow

    missing = [k for k in ("OAUTH_CLIENT_ID", "OAUTH_CLIENT_SECRET") if not env.get(k)]
    if missing:
        sys.exit(f"HATA: .env icinde eksik: {', '.join(missing)}")

    client_config = {
        "installed": {
            "client_id": env["OAUTH_CLIENT_ID"],
            "client_secret": env["OAUTH_CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, scopes)
    creds = flow.run_local_server(
        port=0,
        prompt="consent",
        access_type="offline",
        open_browser=True,
        authorization_prompt_message="  Tarayici acilmazsa su adrese git:\n  {url}\n",
        success_message="Yetkilendirme tamam. Bu sekmeyi kapatabilirsin.",
    )
    save_token(creds)
    return creds


_local = threading.local()


def gmail_service(creds):
    """Thread basina ayri service nesnesi.

    googleapiclient'in http nesnesi thread-safe degil; her thread kendi
    istemcisini kurmali.
    """
    svc = getattr(_local, "svc", None)
    if svc is None:
        from googleapiclient.discovery import build
        svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
        _local.svc = svc
    return svc
