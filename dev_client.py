"""Send one ticket to the Orchestrator as a ChatMessage and print the replies.

Usage: python dev_client.py issues
       python dev_client.py exp1
       python dev_client.py "task: Add a function add(a, b) in src/calc.py ..."
"""

import asyncio
import os
import secrets
import sys

from dotenv import load_dotenv

load_dotenv()
asyncio.set_event_loop(asyncio.new_event_loop())  # Python 3.14 + uagents 0.26.1

from orchestrator import parse_intent  # noqa: E402
from uagents import Agent, Context, Protocol  # noqa: E402
from uagents_core.contrib.protocols.chat import (  # noqa: E402
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    TextContent,
    chat_protocol_spec,
)

PORT = int(os.getenv("DEV_CLIENT_PORT", "8005"))
ORCH = os.environ["ORCHESTRATOR_ADDRESS"]
TICKET = " ".join(sys.argv[1:]) or "task: Add a function add(a, b) in src/calc.py that returns the sum of a and b."

client = Agent(
    name="dev_client",
    seed=secrets.token_hex(16),  # throwaway identity per run
    port=PORT,
    endpoint=[f"http://127.0.0.1:{PORT}/submit"],
    report_events=False,
)
chat = Protocol(spec=chat_protocol_spec)


@chat.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(sender, ChatAcknowledgement(acknowledged_msg_id=msg.msg_id))
    print(f"[orchestrator] {msg.text()}", flush=True)
    is_list = parse_intent(TICKET)[0] in ("list", "help", "show")
    if is_list or any(isinstance(c, EndSessionContent) for c in msg.content):
        print("-- session ended --", flush=True)
        os._exit(0)


@chat.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    print("[orchestrator] ack received", flush=True)


client.include(chat)


@client.on_event("startup")
async def send_ticket(ctx: Context):
    print(f"sending ticket to {ORCH[:20]}...: {TICKET}", flush=True)
    await ctx.send(ORCH, ChatMessage(content=[TextContent(text=TICKET)]))


if __name__ == "__main__":
    client.run()
