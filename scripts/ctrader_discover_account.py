"""
One-shot setup helper — NOT part of the bot's runtime. Run this once,
by hand, after registering a cTrader Open API app (see
docs/ctrader-setup-guide.md) to discover the two values
CTraderOrderExecutor needs that aren't guessable ahead of time:
ctidTraderAccountId (which account the token can act on) and EURUSD's
symbolId (broker-specific — not a universal constant across brokers).

Written against the verified `ctrader-open-api` package API and the
connection/message pattern from the package's own official sample
(github.com/spotware/OpenApiPy/samples/ConsoleSample/main.py) — not
guessed. Has NOT been run against a live account (none existed at
writing time, 2026-09-18). Report back exactly what happens the first
time this actually runs against real credentials.

Usage: python scripts/ctrader_discover_account.py
Prompts for Client ID / Client Secret / redirect URI, walks through the
OAuth consent flow in your browser, then prints every account the token
covers and EURUSD's symbolId for the first one. Exits after printing —
this is a lookup tool, not a long-running connection (the real trading
connection in order_execution.py is separate, future work).
"""

from __future__ import annotations

import sys
import webbrowser

from ctrader_open_api import Auth, Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
    ProtoOAGetAccountListByAccessTokenReq,
    ProtoOAGetAccountListByAccessTokenRes,
    ProtoOASymbolsListReq,
    ProtoOASymbolsListRes,
)
from twisted.internet import reactor

EURUSD_NAME = "EURUSD"


def get_access_token(client_id: str, client_secret: str, redirect_uri: str) -> str:
    auth = Auth(client_id, client_secret, redirect_uri)
    auth_uri = auth.getAuthUri()
    print(f"\nOpening your browser to authorize this app:\n{auth_uri}\n")
    webbrowser.open_new(auth_uri)
    print(
        "After you approve, you'll be redirected to your redirect URI with "
        "?code=... in the address bar. Copy just the code value."
    )
    auth_code = input("Auth Code: ").strip()
    token = auth.getToken(auth_code)
    if "accessToken" not in token:
        raise RuntimeError(f"Token exchange failed, response was: {token}")
    return token["accessToken"]


def main() -> None:
    client_id = input("Client ID: ").strip()
    client_secret = input("Client Secret: ").strip()
    redirect_uri = input("Redirect URI (must match the app's registered one): ").strip()

    access_token = get_access_token(client_id, client_secret, redirect_uri)
    print(f"\nAccess token acquired: {access_token[:8]}... (truncated)\n")

    client = Client(EndPoints.PROTOBUF_DEMO_HOST, EndPoints.PROTOBUF_PORT, TcpProtocol)

    def on_connected(client):
        request = ProtoOAApplicationAuthReq()
        request.clientId = client_id
        request.clientSecret = client_secret
        deferred = client.send(request)
        deferred.addErrback(on_error)

    def on_disconnected(client, reason):
        print(f"\nDisconnected: {reason}")

    def on_message(client, message):
        if message.payloadType == ProtoOAApplicationAuthRes().payloadType:
            print("App authorized. Requesting account list...")
            request = ProtoOAGetAccountListByAccessTokenReq()
            request.accessToken = access_token
            deferred = client.send(request)
            deferred.addErrback(on_error)

        elif message.payloadType == ProtoOAGetAccountListByAccessTokenRes().payloadType:
            response = Protobuf.extract(message)
            account_ids = [acc.ctidTraderAccountId for acc in response.ctidTraderAccount]
            if not account_ids:
                print("No accounts found for this access token.")
                reactor.stop()
                return
            print(f"\nAccounts accessible with this token: {account_ids}")
            first_account_id = account_ids[0]
            print(f"Looking up symbols for account {first_account_id} (using the first one)...")
            request = ProtoOASymbolsListReq()
            request.ctidTraderAccountId = first_account_id
            deferred = client.send(request)
            deferred.addErrback(on_error)

        elif message.payloadType == ProtoOASymbolsListRes().payloadType:
            response = Protobuf.extract(message)
            match = next((s for s in response.symbol if s.symbolName == EURUSD_NAME), None)
            print()
            if match is None:
                print(
                    f"Couldn't find a symbol literally named {EURUSD_NAME!r} — "
                    "print response.symbol yourself to check the naming convention "
                    "this broker uses (some use EURUSD., EUR/USD, etc.)."
                )
            else:
                print(f"{EURUSD_NAME} symbolId: {match.symbolId}")
            print("\nDone. ctidTraderAccountId + symbolId above are what")
            print("CTraderOrderExecutor's constructor needs (see src/order_execution.py).")
            reactor.stop()

    def on_error(failure):
        print(f"\nError: {failure}")
        reactor.stop()

    client.setConnectedCallback(on_connected)
    client.setDisconnectedCallback(on_disconnected)
    client.setMessageReceivedCallback(on_message)
    client.startService()
    reactor.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
