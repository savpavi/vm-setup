#!/usr/bin/env python3
"""Gmail API yetkilendirmesi (OAuth Desktop app) ve dogrulama.

Ilk calistirmada tarayicida onay ister, refresh token'i token.json'a yazar.
Sonraki calistirmalarda sessizce yeniler ve hesap ozetini basar.

    uv run --with google-api-python-client --with google-auth-oauthlib authorize.py
"""
import sys

from gauth import DEFAULT_SCOPE, TOKEN_FILE, get_credentials, gmail_service, load_env


def main():
    env = load_env()
    scopes = [env.get("GWS_SCOPE", DEFAULT_SCOPE)]
    target = env.get("GWS_TARGET_USER", "")

    from googleapiclient.errors import HttpError

    creds = get_credentials(env, scopes)
    svc = gmail_service(creds)

    try:
        prof = svc.users().getProfile(userId="me").execute()
    except HttpError as e:
        status = getattr(e, "status_code", None) or getattr(e.resp, "status", None)
        print(f"\nHATA: Gmail API cagrisi reddedildi ({status}).", file=sys.stderr)
        if status == 403:
            print("  Muhtemel sebep: Gmail API bu projede etkin degil.", file=sys.stderr)
            print(f"  Kontrol: console.cloud.google.com/apis/library/"
                  f"gmail.googleapis.com?project={env.get('GCP_PROJECT_ID','?')}",
                  file=sys.stderr)
        else:
            print(f"  {e}", file=sys.stderr)
        return 1

    actual = prof["emailAddress"]
    print()
    print(f"  Yetkilendirilen hesap : {actual}")
    print(f"  Mevcut mesaj sayisi   : {prof['messagesTotal']}")
    print(f"  Mevcut konu sayisi    : {prof['threadsTotal']}")

    if target and actual.lower() != target.lower():
        print(f"\n  !! UYARI: .env hedefi {target}, onay verilen {actual}.",
              file=sys.stderr)
        print(f"     Yanlissa {TOKEN_FILE} dosyasini sil ve tekrar calistir.",
              file=sys.stderr)
        return 1

    labels = svc.users().labels().list(userId="me").execute().get("labels", [])
    user_labels = sorted(l["name"] for l in labels if l.get("type") == "user")
    print(f"  Mevcut kullanici label: {len(user_labels)}")
    if user_labels:
        print(f"    {', '.join(user_labels[:10])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
