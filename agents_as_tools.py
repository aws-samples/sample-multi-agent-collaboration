"""
Agents as Tools - Peer Expertise on Demand

A primary agent that uses other specialized agents as tools, calling them
when it needs domain expertise. The primary agent doesn't follow a
predefined workflow — it discovers which experts to consult during reasoning.

Prerequisites:
    pip install -r requirements.txt

Learning objectives:
- Understand the agents-as-tools pattern for peer expertise
- See how an agent discovers needed expertise during reasoning
- Learn the difference from sequential pipelines (Lab 07)
- Practice exposing one agent's capabilities to another
"""

import time
from shared.input_utils import get_multiline_input
from shared.streaming import StreamingCallbackHandler
from strands import Agent, tool
from shared.model import get_model


# Specialist agents and the orchestrator are populated inside build_agents()
# and held in this module-level dict so the @tool functions can reach them.
# Each Agent() with a default model creates its own Bedrock client (~8s),
# so all four agents share a single BedrockModel instance.
_AGENTS: dict = {}
_HANDLERS: dict = {}


# --- Domain Specialist Prompts ---

LEGAL_PROMPT = """You are a Legal Specialist Agent.

You provide guidance on contract terms, regulatory compliance, and legal risks.
Be specific about applicable laws and jurisdictions when relevant.
You are NOT a substitute for a real lawyer — frame guidance as starting points
for further legal review.

Keep responses under 200 words."""

FINANCIAL_PROMPT = """You are a Financial Specialist Agent.

You analyze financial implications: cost projections, ROI calculations,
budget impact, cash flow considerations, and accounting treatments.
Show your math when relevant.

Keep responses under 200 words."""

TECHNICAL_PROMPT = """You are a Technical Specialist Agent.

You evaluate technical feasibility: architecture decisions, technology choices,
implementation complexity, and integration risks.
Focus on practical engineering tradeoffs.

Keep responses under 200 words."""

PRIMARY_PROMPT = """You are a Senior Advisor coordinating a team of specialists.

You have three peer experts you can consult:
- consult_legal: For contract, compliance, and regulatory questions
- consult_financial: For costs, ROI, and budget impact
- consult_technical: For feasibility, architecture, and implementation

When given a question:
1. Decide which specialists are relevant — you may need one, two, or all three
2. Formulate a specific question for each relevant specialist
3. Wait for their responses
4. Synthesize the perspectives into a unified recommendation

You are NOT required to consult all specialists for every question.
For purely technical questions, only consult the technical specialist.
For business decisions involving multiple dimensions, consult several.

Provide a final recommendation that integrates the specialist input."""


# --- Expose specialists as tools ---
# These wrappers are defined at module level so the orchestrator can pick
# them up via the @tool decorator. They look up the specialist on demand
# from the _AGENTS dict, which is populated by build_agents().
#
# Each wrapper prints a header before the specialist runs and resets that
# specialist's streaming handler so its response shows up live underneath.

@tool
def consult_legal(question: str) -> str:
    """Consult the Legal Specialist about contracts, compliance, or regulatory questions.

    Args:
        question: Specific legal question or scenario to evaluate
    """
    print("\n  ─── Legal Specialist ───")
    _HANDLERS["legal"].reset()
    response = str(_AGENTS["legal"](question))
    print("\n  ─── Legal Specialist done ───")
    return response


@tool
def consult_financial(question: str) -> str:
    """Consult the Financial Specialist about costs, ROI, or budget impact.

    Args:
        question: Specific financial question or scenario to evaluate
    """
    print("\n  ─── Financial Specialist ───")
    _HANDLERS["financial"].reset()
    response = str(_AGENTS["financial"](question))
    print("\n  ─── Financial Specialist done ───")
    return response


@tool
def consult_technical(question: str) -> str:
    """Consult the Technical Specialist about feasibility, architecture, or implementation.

    Args:
        question: Specific technical question or scenario to evaluate
    """
    print("\n  ─── Technical Specialist ───")
    _HANDLERS["technical"].reset()
    response = str(_AGENTS["technical"](question))
    print("\n  ─── Technical Specialist done ───")
    return response


def build_agents() -> Agent:
    """Construct specialists and orchestrator with a shared Bedrock client.

    Returns the orchestrator agent. Specialists are stored in _AGENTS and
    their streaming handlers in _HANDLERS for the @tool wrappers to use.
    """
    model = get_model()

    # Each specialist gets its own streaming handler so the consult_* tools
    # can reset it before each call. The orchestrator gets its own too.
    _HANDLERS["legal"] = StreamingCallbackHandler()
    _HANDLERS["financial"] = StreamingCallbackHandler()
    _HANDLERS["technical"] = StreamingCallbackHandler()
    _HANDLERS["orchestrator"] = StreamingCallbackHandler()

    _AGENTS["legal"] = Agent(
        system_prompt=LEGAL_PROMPT, model=model, callback_handler=_HANDLERS["legal"],
    )
    _AGENTS["financial"] = Agent(
        system_prompt=FINANCIAL_PROMPT, model=model, callback_handler=_HANDLERS["financial"],
    )
    _AGENTS["technical"] = Agent(
        system_prompt=TECHNICAL_PROMPT, model=model, callback_handler=_HANDLERS["technical"],
    )

    primary = Agent(
        system_prompt=PRIMARY_PROMPT,
        model=model,
        tools=[consult_legal, consult_financial, consult_technical],
        callback_handler=_HANDLERS["orchestrator"],
    )
    _AGENTS["orchestrator"] = primary
    return primary


def main():
    """Run the agents-as-tools agent."""
    print("Agents as Tools - Peer Expertise on Demand")
    print("=" * 40)
    print("A coordinator agent decides which specialist agents to consult")
    print("based on the question. No predefined workflow — the coordinator")
    print("discovers needed expertise during reasoning.\n")

    # Defer Bedrock init so the user sees the framing immediately rather
    # than staring at a blank terminal during the boto3 client init.
    print("Initializing Bedrock client...")
    init_start = time.time()
    primary_agent = build_agents()
    print(f"✓ Ready ({time.time() - init_start:.1f}s)\n")

    print("Type 'quit' to exit\n")
    print("Choose a question (pick a number, or type your own):")
    print("  1. [1 specialist] Migrate our main API from REST to GraphQL — what are the")
    print("     technical implications?")
    print("  2. [2 specialists] Build a custom CRM ($400k upfront + $100k/yr) or buy")
    print("     Salesforce ($200k/yr) — which should we choose?")
    print("  3. [3 specialists] Offer AI-generated legal docs (contracts, NDAs, policies)")
    print("     to customers at $50/month — what are the major considerations?\n")

    prompts = {
        "1": "We're considering migrating our main API from REST to GraphQL. What are the technical implications I should know about?",
        "2": "We're evaluating whether to build a custom CRM or buy Salesforce. Cost is $200k/year for Salesforce vs an estimated $400k upfront + $100k/year maintenance for custom build. What should we choose?",
        "3": "We're considering offering AI-generated legal document drafts to customers. The product would generate contracts, NDAs, and policies. Customers would pay $50/month. What are the major considerations across legal, financial, and technical dimensions?",
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
            print("\n  ─── Coordinator ───")
            _HANDLERS["orchestrator"].reset()
            start_time = time.time()
            primary_agent(user_input)
            elapsed = time.time() - start_time
            print(f"\n  ✓ Coordinator complete ({elapsed:.1f}s)\n")
        except Exception as e:
            print(f"\nError: {e}\n")


if __name__ == "__main__":
    main()
