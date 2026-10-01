"""
Swarm Handoff - Decentralized Agent Collaboration

A swarm of AWS specialists answers a customer's architecture question.
Each specialist holds factual expertise in one domain (Bedrock, databases,
compute). When a question crosses into a peer's domain, the active agent
hands off — because making up specialist facts would be wrong, and the
peer holds the accurate information.

Unlike Lab 7's sequential workflow (where the order is fixed), the path
through this swarm depends on which domains the question hits and which
order the specialists encounter the gaps. Different scenarios produce
different chains — and that's the point.

Prerequisites:
    pip install -r requirements.txt

Learning objectives:
- Understand peer-to-peer agent collaboration via handoffs
- See specialist agents stay in their lane and defer to peers
- Observe handoff chains emerge from the question's domain demands
- Compare with Lab 7's sequential workflow on the same kind of problem
"""

import asyncio
import time
from shared.input_utils import get_multiline_input
from strands import Agent
from shared.model import get_model
from strands.multiagent import Swarm


# --- Specialist Agent Prompts ---
# Each agent owns a domain and knows what it CAN'T see. 
# Each agent's job is to form a hypothesis, gather what evidence
# it can from its own domain, and hand off when confirming the hypothesis
# requires another specialist's view.
#
# Agents are constructed inside build_swarm() with a SHARED BedrockModel.
# Constructing each agent with its own default model creates a separate
# Bedrock client per agent (~8s each, so 3 agents = ~24s). Sharing one
# model brings setup down to a single Bedrock client init.

INFRA_PROMPT = """You are an Amazon Bedrock specialist agent.

You have deep, accurate knowledge of:
- Bedrock model families: Claude (Haiku, Sonnet, Opus), Nova (Micro, Lite,
  Pro, Premier), Llama, Titan — including their pricing, context windows,
  latency characteristics, and use-case fit.
- Bedrock Knowledge Bases (managed RAG, supported vector store backends,
  chunking, ingestion).
- Bedrock Agents and AgentCore for agentic workflows.
- Inference profiles (us.* and global.* IDs), provisioned vs on-demand
  throughput, and region availability.

You do NOT claim specialist accuracy on:
- Database internals — RDS, Aurora, DynamoDB, OpenSearch, ElastiCache
  sizing, schema design, or pricing. For database-specific questions,
  consult 'database_specialist' to ensure accurate information.
- Compute, runtime, or networking — Lambda, ECS, EKS, EC2, VPC,
  Step Functions sizing, deployment, or pricing. For those, consult
  'compute_specialist'.

How to respond:
- If the question (or the part you've been given) is about Bedrock — model
  choice, RAG approach, agent design, inference cost — answer with specifics.
  Cite token prices, latency numbers, model names.
- If the question crosses into a peer's domain — hand off the relevant part
  with enough context for them to answer accurately. Don't guess.
- If a peer hands off a question and it's in your domain — answer it.
  Don't bounce it back.

Synthesis: when the customer's question includes constraints (budget,
latency, throughput) the answer is a recommendation that VALIDATES against
those constraints — the numbers from all specialists need to be combined
and checked. If you first received the question, you own the synthesis.
After your peers have contributed their pieces and numbers, assemble the
final recommendation and verify it meets the customer's constraints.
If a peer has handed back to you for synthesis, do that work and stop.

Stay concise. Stay in your lane. Defer to peers for their domains."""

APP_PROMPT = """You are an AWS compute specialist agent.

You have deep, accurate knowledge of:
- Lambda — memory tiers, billing model, cold starts, provisioned
  concurrency, VPC attachment, runtime choices, layer limits.
- ECS, EKS, Fargate, EC2 — when each fits, sizing tradeoffs, pricing.
- Step Functions, Kinesis, SQS, EventBridge — orchestration and event
  patterns, throughput and cost.
- VPC networking — subnets, NAT, VPC endpoints, security groups.

You do NOT claim specialist accuracy on:
- Bedrock models, RAG architecture, or AI inference cost. For those,
  consult 'bedrock_specialist'.
- Database design, sizing, or pricing — RDS, Aurora, DynamoDB, OpenSearch.
  For those, consult 'database_specialist'.

How to respond:
- If the question is about Lambda, ECS, networking, or orchestration —
  answer with specifics. Cite memory sizes, pricing per request/GB-second,
  cold start ranges, throughput limits.
- If it crosses into a peer's domain — hand off with enough context.
- If a peer hands off a question in your domain — answer it directly.

Synthesis: when the customer's question includes constraints (budget,
latency, throughput), the final answer needs to combine all specialists'
numbers and verify the constraints are met. If you first received the
question, you own that synthesis. Otherwise, after you've contributed
your part, hand back to whoever first received the question so they can
assemble the totals and confirm the constraints fit.

Stay concise. Stay in your lane."""

DATA_PROMPT = """You are an AWS database and storage specialist agent.

You have deep, accurate knowledge of:
- DynamoDB — table design, partition keys, GSIs, on-demand vs provisioned,
  consistency models, item size limits, pricing.
- RDS and Aurora — engines (Postgres, MySQL), Aurora Serverless v2, Aurora
  pgvector for embeddings, pricing.
- OpenSearch (provisioned and Serverless) — sizing, ingestion, vector
  search, pricing.
- ElastiCache (Redis, Memcached), S3 (intelligent tiering, query patterns),
  Timestream for time-series.

You do NOT claim specialist accuracy on:
- Bedrock model choice, RAG inference flow, or agent architecture. For
  those, consult 'bedrock_specialist'.
- Lambda, ECS, networking, or orchestration. For those, consult
  'compute_specialist'.

How to respond:
- If the question is about database or storage choice, schema, or pricing —
  answer with specifics. Cite RCU/WCU costs, OpenSearch instance pricing,
  Aurora pricing per ACU-hour.
- If it crosses into a peer's domain — hand off with context.
- If a peer hands off a question in your domain — answer it.

Synthesis: when the customer's question includes constraints (budget,
latency, throughput), the final answer needs to combine all specialists'
numbers and verify the constraints are met. If you first received the
question, you own that synthesis. Otherwise, after you've contributed
your part, hand back to whoever first received the question so they can
assemble the totals and confirm the constraints fit.

Stay concise. Stay in your lane."""


def _extract_text(node_result) -> str:
    """Pull the assistant's text out of a NodeResult."""
    if node_result is None:
        return ""
    try:
        content = node_result.result.message.get("content", [])
        return "\n".join(c.get("text", "") for c in content if "text" in c).strip()
    except (AttributeError, KeyError):
        return ""


def _wrap(text: str, indent: str = "      ", width: int = 90) -> str:
    """Indent a text block and soft-wrap long lines for terminal readability."""
    out_lines = []
    for line in text.splitlines() or [""]:
        if not line:
            out_lines.append(indent)
            continue
        # Soft wrap on word boundaries.
        while len(line) > width:
            split = line.rfind(" ", 0, width)
            if split == -1:
                split = width
            out_lines.append(indent + line[:split])
            line = line[split:].lstrip()
        out_lines.append(indent + line)
    return "\n".join(out_lines)


async def run_swarm_streaming(swarm: Swarm, task: str):
    """Run the swarm with stream_async, printing live agent activity.

    Strands' stream_async yields five event types. We surface the three the
    user cares about (start, handoff, stop) and skip the high-volume token
    stream events so the output stays readable.
    """
    node_starts: dict[str, float] = {}
    node_stop_text: dict[str, str] = {}
    node_history: list[str] = []
    final_result = None

    async for event in swarm.stream_async(task):
        et = event.get("type")

        if et == "multiagent_node_start":
            node_id = event["node_id"]
            node_starts[node_id] = time.time()
            node_history.append(node_id)
            print(f"\n  ▶ {node_id} reasoning...")

        elif et == "multiagent_handoff":
            from_id = (event.get("from_node_ids") or ["?"])[0]
            to_id = (event.get("to_node_ids") or ["?"])[0]
            msg = event.get("message", "").strip()
            print(f"\n  ↪ handoff: {from_id} → {to_id}")
            if msg:
                print(_wrap(msg))

        elif et == "multiagent_node_stop":
            node_id = event["node_id"]
            elapsed = time.time() - node_starts.get(node_id, time.time())
            text = _extract_text(event.get("node_result"))
            node_stop_text[node_id] = text
            print(f"  ✓ {node_id} done ({elapsed:.1f}s)")

        elif et == "multiagent_result":
            final_result = event.get("result")

        # multiagent_node_stream events are per-token; suppress for cleanliness.

    # The final recommendation is whichever node ended the swarm without
    # handing off. If the swarm hit the handoff cap mid-conversation, fall
    # back to showing the last node's stop text — which will be a handoff
    # request, but at least gives the user something to read.
    final_text = ""
    if node_history:
        final_text = node_stop_text.get(node_history[-1], "")

    return final_result, node_history, final_text


def build_swarm() -> Swarm:
    """Build the architecture-recommendation swarm with a shared Bedrock client.

    Why a shared model: each Agent() with no explicit model creates its own
    BedrockModel, and each BedrockModel constructor initializes a boto3
    Bedrock client (~8s on cold start). Three agents = ~24s of redundant
    init. One shared model = one client init.
    """
    model = get_model()

    bedrock = Agent(
        name="bedrock_specialist",
        system_prompt=INFRA_PROMPT,
        model=model,
        callback_handler=None,
    )
    compute = Agent(
        name="compute_specialist",
        system_prompt=APP_PROMPT,
        model=model,
        callback_handler=None,
    )
    database = Agent(
        name="database_specialist",
        system_prompt=DATA_PROMPT,
        model=model,
        callback_handler=None,
    )

    return Swarm(
        nodes=[bedrock, compute, database],
        # No fixed entry point per question — first agent in nodes receives
        # input. The swarm chooses its own path from there. Bedrock is a
        # sensible first responder because all three example questions are
        # GenAI architecture questions; the customer's framing is in
        # bedrock_specialist's domain.
        max_handoffs=8,
        max_iterations=8,
    )


def main():
    """Run the architecture-recommendation swarm interactively."""
    print("Swarm Handoff - AWS Architecture Specialists")
    print("=" * 40)
    print("Three specialists collaborate to answer customer architecture")
    print("questions: a Bedrock specialist, a compute specialist, and a")
    print("database specialist. Each handles questions in its own domain")
    print("and hands off when the question crosses into a peer's domain")

    # Defer Bedrock client initialization until after the menu prints, so the
    # user sees the lab's framing immediately rather than staring at a blank
    # terminal during the boto3 client init.
    print("Initializing Bedrock client...")
    init_start = time.time()
    swarm = build_swarm()
    print(f"✓ Ready ({time.time() - init_start:.1f}s)\n")

    print("Type 'quit' to exit.\n")
    print("Choose a customer architecture question (pick a number, or type your own):")
    print("  1. Build an internal Q&A chatbot over a 5GB doc set, in VPC, <$500/mo")
    print("  2. Real-time sentiment scoring on 10K events/sec with dashboards")
    print("  3. Migrate a daily on-prem ML batch job (100GB CSV) to AWS native\n")

    prompts = {
        "1": (
            "Customer question: We're building an internal customer-support "
            "chatbot. It should answer questions over our product documentation "
            "(about 5 GB across PDFs and Confluence exports). Constraints: "
            "responses under 2 seconds, must run inside our VPC for compliance, "
            "total infrastructure cost under $500/month at 200 queries per "
            "minute. We've decided NOT to use Bedrock Knowledge Bases — we "
            "want to manage our own vector store so we can swap embedding "
            "models later. Please recommend three things, with pricing and "
            "latency numbers for each: (1) the Bedrock model for generation; "
            "(2) the AWS database service that backs the vector store; "
            "(3) the compute service that orchestrates retrieval and inference."
        ),
        "2": (
            "Customer question: We're building a real-time analytics pipeline. "
            "Customer-feedback events arrive on Kinesis Data Streams at about "
            "1,000 events per second (peak 1,500). Each event needs sentiment "
            "analysis applied via a Bedrock model, then the enriched event "
            "needs to be queryable in a dashboard with sub-30-second freshness. "
            "We have a hard total monthly infrastructure budget of $8,000 and "
            "a hard end-to-end latency target of 5 seconds from event arrival "
            "to dashboard visibility. Please recommend three things, with "
            "throughput, latency, and cost numbers: (1) the Bedrock model "
            "that handles this volume cost-effectively; (2) the storage layer "
            "that makes events queryable inside 30s; (3) the compute / "
            "consumer pattern that pulls from Kinesis and orchestrates the "
            "inference and write — for example Lambda vs Managed Flink vs "
            "ECS. Confirm the totals fit the $8,000 / 5-second targets."
        ),
        "3": (
            "Customer question: We have a daily on-prem batch ML pipeline. It "
            "reads ~100 GB of CSV from a file share, runs a Python data-prep "
            "step, calls our internal forecasting model, and writes results to "
            "a Postgres database that powers internal dashboards. We want to "
            "migrate everything to AWS-native services. We currently spend "
            "about $3,000/month operating this pipeline on-prem and we need "
            "the AWS target to stay at or below that to justify the move. "
            "The daily batch must finish within a 4-hour window. Please "
            "recommend three things, with cost and operational tradeoffs: "
            "(1) where the forecasting model should run — Bedrock vs "
            "self-hosted; (2) the AWS database service that replaces "
            "Postgres for the dashboards; (3) the compute service that runs "
            "the daily batch pipeline. Confirm the totals fit the "
            "$3,000/month / 4-hour-window targets."
        ),
    }

    while True:
        user_input = get_multiline_input("You: ").strip()

        if user_input.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break

        if not user_input:
            continue

        # A menu number expands to its canned prompt; anything else is sent
        # to the agent as-is so you can try your own scenarios.
        if user_input in prompts:
            user_input = prompts[user_input]

        try:
            print("\n    ─── Architecture swarm started ───")
            start_time = time.time()
            final_result, node_history, final_text = asyncio.run(
                run_swarm_streaming(swarm, user_input)
            )
            elapsed = time.time() - start_time

            print(f"\n    ─── Swarm complete ({elapsed:.1f}s) ───")

            # The handoff chain is the part that differs from a workflow. With
            # a workflow you already know the order. Here you don't until the
            # swarm runs.
            if node_history:
                print(f"    Handoff chain: {' → '.join(node_history)}")
                print(f"    Total handoffs: {max(0, len(node_history) - 1)}")

            if final_result is not None and hasattr(final_result, "accumulated_usage"):
                usage = final_result.accumulated_usage
                if isinstance(usage, dict):
                    total = usage.get("totalTokens")
                    if total is not None:
                        print(f"    Tokens used: {total}")

            print("\nRecommendation:")
            print(_wrap(final_text or "(no recommendation returned)", indent="  "))
            print()
        except Exception as e:
            print(f"\nError: {e}\n")


if __name__ == "__main__":
    main()
