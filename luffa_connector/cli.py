"""
CLI entry points:
  luffa-agent      — start an AI agent on Luffa
  luffa-discovery  — start the agent discovery service
"""
import asyncio
import argparse
import os
import sys
from dotenv import load_dotenv


def agent_main():
    """
    Entry point for `luffa-agent` command.
    All args are optional — defaults come from .env or environment variables.
    """
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="luffa-agent",
        description="Connect an AI agent to the Luffa messaging platform.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment variables (can be set in .env instead of passing flags):
  LUFFA_ROBOT_SECRET   Bot secret from robot.luffa.im        (required)
  LUFFA_BOT_UID        Your bot's Luffa UID                   (recommended)
  OWNER_LUFFA_UID      Your personal Luffa UID                (optional)
  VLLM_BASE_URL        vLLM server URL                        (default: http://localhost:8000/v1)
  VLLM_MODEL           Model name                             (default: Qwen/Qwen2.5-7B-Instruct-AWQ)
  AGENT_NAME           Name shown in discovery                (default: LuffaAgent)
  AGENT_DID            Agent DID                              (auto-generated if not set)
  DISCOVERY_URL        Discovery service URL                   (default: http://localhost:8002)

Examples:
  luffa-agent
  luffa-agent --name "Atlas" --capabilities research translation
  luffa-agent --secret XXX --owner-uid YYY --bot-uid ZZZ
        """,
    )
    parser.add_argument("--secret",       help="Luffa robot secret (overrides LUFFA_ROBOT_SECRET)")
    parser.add_argument("--bot-uid",      help="Bot's own Luffa UID (overrides LUFFA_BOT_UID)")
    parser.add_argument("--owner-uid",    help="Owner's Luffa UID (overrides OWNER_LUFFA_UID)")
    parser.add_argument("--name",         help="Agent name shown in discovery (overrides AGENT_NAME)")
    parser.add_argument("--did",          help="Agent DID (overrides AGENT_DID)")
    parser.add_argument("--vllm-url",     help="vLLM base URL (overrides VLLM_BASE_URL)")
    parser.add_argument("--model",        help="Model name (overrides VLLM_MODEL)")
    parser.add_argument("--discovery",    help="Discovery service URL (overrides DISCOVERY_URL)")
    parser.add_argument("--no-safety",    action="store_true", help="Disable safety filters")
    parser.add_argument("--capabilities", nargs="*", default=[], metavar="CAP",
                        help="Capabilities to advertise e.g. --capabilities research translation")

    args = parser.parse_args()

    from luffa_connector import LuffaConnector

    try:
        connector = LuffaConnector(
            bot_secret=args.secret,
            bot_luffa_uid=args.bot_uid,
            owner_uid=args.owner_uid,
            agent_name=args.name,
            agent_did=args.did,
            vllm_url=args.vllm_url,
            model=args.model,
            discovery_url=args.discovery,
            capabilities=args.capabilities or None,
            enable_safety=not args.no_safety,
        )
    except EnvironmentError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        asyncio.run(connector.start())
    except KeyboardInterrupt:
        print("\nShutting down.")


def discovery_main():
    """Entry point for `luffa-discovery` command."""
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="luffa-discovery",
        description="Start the Luffa agent discovery service.",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8002, help="Port to listen on (default: 8002)")
    args = parser.parse_args()

    import uvicorn
    print(f"Starting discovery service on {args.host}:{args.port}")
    uvicorn.run("luffa_discovery.app:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    agent_main()
