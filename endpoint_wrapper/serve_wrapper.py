"""CLI: serve an LLM loop that wraps an external endpoint.

    python -m agent_skeleton.endpoint_wrapper --card my.card.json \
        --endpoint-url https://api.example.com/run

The endpoint URL is public (it goes in the card); the auth TOKEN is read at call
time from the env var NAMED by --endpoint-auth-env, so no secret is stored in code
or the card.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from ..a2a_runtime import require_a2a
from ..config import AGENT_NAME, DEFAULT_CARD_PATH, env_advertise_url, env_host, env_model, env_port
from ..serve import create_app, load_agent_card
from .call_endpoint import EndpointConfig
from .specs import endpoint_wrapper_spec


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Serve an LLM endpoint-wrapper agent.")
    p.add_argument("--model", default=env_model())
    p.add_argument("--host", default=env_host())
    p.add_argument("--port", type=int, default=env_port())
    p.add_argument("--card", type=Path, default=DEFAULT_CARD_PATH)
    p.add_argument("--advertise-url", default=env_advertise_url())
    p.add_argument("--endpoint-url", default=os.getenv("AGENT_ENDPOINT_URL"),
                   help="URL of the external service to wrap.")
    p.add_argument("--endpoint-protocol", default=os.getenv("AGENT_ENDPOINT_PROTOCOL", "http"),
                   choices=["http", "a2a"])
    p.add_argument("--endpoint-method", default=os.getenv("AGENT_ENDPOINT_METHOD", "POST"))
    p.add_argument("--endpoint-auth-env", default=os.getenv("AGENT_ENDPOINT_AUTH_ENV"),
                   help="NAME of the env var holding the upstream auth token (not the token).")
    p.add_argument("--io-criteria", default="", help="Notes on the endpoint's expected input/output.")
    return p


def main() -> None:
    args = build_parser().parse_args()
    if not args.endpoint_url:
        raise SystemExit("endpoint-wrapper requires --endpoint-url (or AGENT_ENDPOINT_URL).")

    require_a2a()
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("The uvicorn package is required to serve.") from exc

    card = load_agent_card(args.card)
    if args.advertise_url:
        try:
            card = card.model_copy(update={"url": args.advertise_url})
        except Exception:
            card.url = args.advertise_url

    endpoint = EndpointConfig(
        url=args.endpoint_url,
        method=args.endpoint_method,
        protocol=args.endpoint_protocol,
        auth_env=args.endpoint_auth_env,
    )
    spec = endpoint_wrapper_spec(
        name=getattr(card, "name", AGENT_NAME),
        endpoint=endpoint,
        description=getattr(card, "description", "") or "",
        io_criteria=args.io_criteria,
        model=args.model,
    )
    print(f"Serving endpoint-wrapper {getattr(card, 'name', AGENT_NAME)} on {args.host}:{args.port}")
    uvicorn.run(create_app(card, model=args.model, spec=spec), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
