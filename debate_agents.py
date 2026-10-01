"""
Debate Agents - Iterative Refinement Through Disagreement

Two agents work in opposition: a Proposer suggests a solution, and a
Critic challenges it. They iterate until the Critic accepts the proposal
or a maximum number of rounds is reached. Demonstrates how emergent
quality comes from negotiation rather than from one perfect first answer.

The conversation streams to the terminal as it happens — each agent's
response appears token-by-token via the shared StreamingCallbackHandler,
so you can watch the back-and-forth unfold in real time.

Prerequisites:
    pip install -r requirements.txt

Learning objectives:
- Understand the proposer/critic pattern for iterative refinement
- See how disagreement produces better outputs than agreement
- Learn to design constructive critic agents that don't just rubber-stamp
- Practice multi-round agent dialogue with live streaming output
"""

import time
from shared.input_utils import get_multiline_input
from shared.streaming import StreamingCallbackHandler
from strands import Agent
from shared.model import get_model


PROPOSER_PROMPT = """You are a Proposer Agent. Your job is to generate solutions
to problems and refine them based on feedback from a Critic.

When given a task:
1. Provide a complete, specific solution
2. If you receive criticism, take it seriously and revise
3. Don't just defend your previous answer — actually incorporate the feedback
4. Each revision should be measurably better than the previous version

Be willing to admit when criticism is valid. Be willing to push back when it isn't,
but explain why. The goal is the best final answer, not winning the debate.

Keep responses focused and concise."""

CRITIC_PROMPT = """You are a Critic Agent. Your job is to evaluate proposals from
a Proposer and identify weaknesses, gaps, or errors.

When evaluating a proposal:
1. Be specific about what's wrong — not just "this could be better"
2. Identify missing considerations the Proposer overlooked
3. Challenge weak reasoning or unsupported claims
4. Suggest concrete improvements when you can

Don't be a yes-agent. Find real issues. But also don't manufacture problems
where none exist.

End your critique with one of:
- VERDICT: REVISE — if the proposal needs work
- VERDICT: ACCEPT — if the proposal is genuinely good

Be willing to accept good work. Be willing to push back on weak work."""


def build_agents() -> tuple[Agent, Agent, StreamingCallbackHandler, StreamingCallbackHandler]:
    """Construct proposer and critic with a shared Bedrock client.

    Each Agent() with a default model creates its own Bedrock client (~8s),
    so we share one BedrockModel between both. Each agent also gets its own
    StreamingCallbackHandler so the conversation streams live.
    """
    model = get_model()
    proposer_handler = StreamingCallbackHandler()
    critic_handler = StreamingCallbackHandler()
    proposer = Agent(
        system_prompt=PROPOSER_PROMPT, model=model, callback_handler=proposer_handler,
    )
    critic = Agent(
        system_prompt=CRITIC_PROMPT, model=model, callback_handler=critic_handler,
    )
    return proposer, critic, proposer_handler, critic_handler


def _run_stage(name: str, agent: Agent, handler: StreamingCallbackHandler, prompt: str) -> str:
    """Run one debate stage with streamed output. Returns the assembled text."""
    print(f"\n  ─── {name} ───\n")
    handler.reset()
    response = agent(prompt)
    print()  # close the streamed line cleanly
    return str(response)


def run_debate(
    proposer: Agent,
    critic: Agent,
    proposer_handler: StreamingCallbackHandler,
    critic_handler: StreamingCallbackHandler,
    task: str,
    max_rounds: int = 3,
) -> tuple[str, int, bool]:
    """Run a debate with live streaming. Returns (final_proposal, rounds, accepted)."""

    proposal = _run_stage(
        "Round 1 — Proposer", proposer, proposer_handler, task,
    )

    accepted = False
    rounds_used = 1

    for round_num in range(2, max_rounds + 2):
        critique = _run_stage(
            f"Round {round_num - 1} — Critic",
            critic,
            critic_handler,
            f"Evaluate this proposal:\n\nORIGINAL TASK: {task}\n\n"
            f"PROPOSAL:\n{proposal}",
        )

        if "VERDICT: ACCEPT" in critique.upper():
            accepted = True
            print(f"  ✓ Critic accepted the proposal in round {round_num - 1}")
            break

        if round_num > max_rounds:
            print("  ⚠ Max rounds reached without acceptance")
            break

        proposal = _run_stage(
            f"Round {round_num} — Proposer (revised)",
            proposer,
            proposer_handler,
            f"Your original proposal:\n{proposal}\n\n"
            f"The Critic responded:\n{critique}\n\n"
            f"Revise your proposal to address the valid criticisms.",
        )
        rounds_used = round_num

    return proposal, rounds_used, accepted


def main():
    """Run the debate agents."""
    print("Debate Agents - Iterative Refinement Through Disagreement")
    print("=" * 40)
    print("A Proposer and Critic iterate up to 3 rounds. Each round,")
    print("the Critic identifies weaknesses, and the Proposer revises.")
    print("The debate ends when the Critic accepts or rounds run out.")
    print("Conversation streams live as each agent responds.\n")

    # Defer Bedrock init so the user sees the framing immediately rather
    # than staring at a blank terminal during the boto3 client init.
    print("Initializing Bedrock client...")
    init_start = time.time()
    proposer, critic, proposer_handler, critic_handler = build_agents()
    print(f"✓ Ready ({time.time() - init_start:.1f}s)\n")

    print("Type 'quit' to exit\n")
    print("Choose a topic (pick a number, or type your own):")
    print("  1. Design decision (caching strategy)")
    print("  2. Hiring decision (junior vs senior engineer)")
    print("  3. Product positioning (target audience)\n")

    prompts = {
        "1": "Recommend a caching strategy for a read-heavy API serving 10,000 requests per second. Be specific about technology choices and tradeoffs.",
        "2": "Should a 5-person startup with $1M in seed funding hire one senior engineer at $200k or two junior engineers at $90k each? Justify your recommendation.",
        "3": "We're launching a productivity app. Should we target individual professionals or sell to enterprises? Recommend an approach with reasoning.",
    }

    while True:
        user_input = get_multiline_input("You: ").strip()

        if user_input.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break

        if not user_input:
            continue

        # A menu number expands to its canned task; anything else is used
        # as the task so you can try your own scenarios.
        task = prompts.get(user_input, user_input)

        try:
            start_time = time.time()
            _, rounds, accepted = run_debate(
                proposer, critic, proposer_handler, critic_handler,
                task, max_rounds=3,
            )
            elapsed = time.time() - start_time

            print(f"\n  {'═' * 38}")
            print("  DEBATE COMPLETE")
            print(f"  {'═' * 38}")
            print(f"  Rounds used: {rounds}")
            print(f"  Outcome: {'Accepted by critic' if accepted else 'Max rounds reached'}")
            print(f"  Total time: {elapsed:.1f}s\n")
        except Exception as e:
            print(f"\nError: {e}\n")


if __name__ == "__main__":
    main()
