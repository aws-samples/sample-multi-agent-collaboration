# When Multi-Agent Collaboration Earns Its Cost

*A guide to picking — and skipping — multi-agent patterns based on what your problem actually needs*

---

This is the eleventh and final post in our series on [AWS Prescriptive Guidance for Agentic AI Patterns](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-patterns/). Each post focuses on the concepts and patterns behind a single agent type, paired with a [hands-on sample on GitHub](README.md).

## Introduction

Multi-agent collaboration is one of the most capable patterns in agentic AI. A team of peer agents, each with distinct expertise, coordinating on a single goal without a central script. When it works, nothing else delivers the same depth of reasoning. When it doesn't, the cost shows up in tokens, latency, and failure modes a single agent doesn't have. Sometimes, a single agent may outperform multiple specialized agents anyway. The skill is less in building the architecture, than in knowing when to.

This post is about that judgment call: when multi-agent reliably outperforms a single agent, how to assign the work correctly, and a few example patterns: swarm handoff, agents-as-tools, and debate. It builds on [Sample 07](https://github.com/aws-samples/sample-workflow-orchestration-agent/blob/main/Orchestrating%20Agents%20-%20Sequential%2C%20Parallel%2C%20and%20Conditional%20Workflows.md) which ran a fixed plan through specialists. Here, peer agents coordinate as the problem unfolds, with the path through them emerging at runtime.

By the end of this post, you'll understand:
- Why multi-agent systems cost several times more than a single agent
- A few situations where multi-agent reliably outperforms one agent
- The decomposition mistake that makes most multi-agent projects fail
- Some collaboration patterns: swarm handoff, agents-as-tools, and debate

---

## The Road to Multi-Agent Systems: A Brief History

The idea of many simple agents producing intelligent collective behavior is older than LLMs.

### Multi-agent systems in classical AI

Multi-agent systems aren't new. Decades before generative AI, researchers built systems where independent software agents communicated, negotiated, and solved problems together. Swarm intelligence drew on concepts from biology, ant colonies and flocking birds, to show that simple agents following local rules could produce sophisticated global behavior without any central controller.

### LLM agents and the orchestration wave

When LLMs made each agent individually capable, the natural next move was to wire several together. Frameworks for multi-agent LLM systems proliferated, and the early enthusiasm assumed more agents meant more capability. Teams built elaborate role-based architectures on that assumption.

### The cost reckoning (2024-2026)

Practice tempered the hype. [Anthropic's analysis](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them) found multi-agent implementations typically use **3–10x more tokens** than single-agent approaches for equivalent work. Their flagship [Research feature](https://www.anthropic.com/engineering/multi-agent-research-system) uses roughly 15x. Cognition, the team behind Devin, went further in [Don't Build Multi-Agents](https://cognition.com/blog/dont-build-multi-agents), arguing that parallel subagents make implicit, conflicting decisions that drag down the final answer.

---

## The Cost Is Real

Those two positions, multi and single agent, aren't contradictory, both are right under certain conditions. The asymmetry is what matters: when multi-agent works, the wins are real (Anthropic reports a [~90% improvement](https://www.anthropic.com/engineering/multi-agent-research-system) on their internal research benchmark in June 2025); when it doesn't, you've spent months and many times the inference budget for no improvement. [Anthropic also reports](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them) watching teams invest heavily in elaborate architectures only to find that better prompting of a *single* agent matched the result.

So the default should be a single, well-prompted agent. Reach for multi-agent only when it solves a constraint one agent cannot and don't use it as a targeted goal.

---

## When Multi-Agent Earns Its Cost

Drawn from [Anthropic's framework](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them) based on production deployments, there are three legitimate cases where multi-agent reliably beats single-agent:

- **Context protection.** A subtask generates a high volume of context that's irrelevant to the rest of the task. Isolating it in a subagent that returns only a summary keeps the main agent's reasoning clean.
- **Parallelization.** Independent subtasks with no shared mutable state — research facets, multi-source verification, fan-out workloads — can run concurrently.
- **Specialization.** When one agent's tool count grows past ~20, when behavioral modes conflict (an empathetic support agent and a strict compliance reviewer don't share a prompt comfortably), or when domain context would overwhelm a generalist.

---

## The Decomposition Mistake

The most common multi-agent failure isn't a bug, but rather a design choice that sounds reasonable: **split the work by role.** Imagine a feature-shipping system with a planner, an implementer, a tester, and a reviewer. Four agents, clean separation of concerns. It fails reliably, because the four roles share enormous context: the tester needs to know why the implementer made its choices, the reviewer needs the iteration history. Each handoff loses fidelity, and the team spends more tokens shuttling context than doing the work. [Cognition's critique](https://cognition.com/blog/dont-build-multi-agents) of this pattern names the underlying principle: agents that work on the same goal need to share context, and every action one agent takes carries implicit decisions the others can't infer from a summary.

The right question isn't "how do I split this by role?" but "**where can I draw a context boundary?**" Agents earn separation when they operate on genuinely separate context. Researching market trends in Asia versus Europe is a clean split if neither agent needs the other's findings. Writing a feature then testing it is not.

---

## Three Collaboration Patterns

<img src="images/multi-agent-collaboration.png" width="600" alt="Diagram of multi-agent collaboration: a task is distributed across role-specialized peer agents that communicate and negotiate, then synthesize their contributions into a final result." />

When multi-agent does fit, it takes recognizable patterns. The companion sample builds three.

| Pattern | What it is | Earns its cost when |
|---------|-----------|---------------------|
| **Swarm handoff** | Peer agents hand off based on the question's domain | Each specialist holds distinct knowledge and the path depends on the question |
| **Agents as tools** | An orchestrator consults specialists as callable tools | The orchestrator must decide *which* experts a given problem needs |
| **Debate** | A proposer and critic iterate across rounds | Adversarial pressure produces a better answer than one pass |

A **swarm** is decentralized: peers defer to each other with no central router, so the handoff chain emerges from the question. **Agents-as-tools** keeps an orchestrator in charge but lets it discover which specialists to consult mid-reasoning. **Debate** pits a proposer against a critic for self-correction, surfacing flaws a single pass would miss.

>**Note:** The agents-as-tools pattern can sound similar to [Sample 07's conditional router](https://github.com/aws-samples/sample-workflow-orchestration-agent/blob/main/Orchestrating%20Agents%20-%20Sequential%2C%20Parallel%2C%20and%20Conditional%20Workflows.md). The difference is that an agents-as-tools orchestrator holds the conversation and can consult several specialists iteratively (or the same one repeatedly), whereas Sample 07's router classifies the request once and dispatches it to a single specialist who answers alone.

---

## When to Use Multi-Agent Collaboration

Use it for open-ended problems that benefit from diverse perspectives or genuine parallelism.

| Use Case | Example |
|----------|---------|
| **Autonomous research teams** | A search agent, summarizer, and validator working in parallel |
| **Business scenario modeling** | Finance, policy, and compliance perspectives on one decision |
| **Negotiation & multiparty reasoning** | Agents representing competing interests |
| **Multimodal tasks** | Combining image, text, and logic across specialists |
| **Deliberation** | Proposer/critic debate for high-stakes decisions |

### When a Single Agent Wins

If the work shares context, fits one agent's tools and prompt, and doesn't parallelize cleanly, a single agent is cheaper, faster, and easier to debug. The honest default for most problems is one well-prompted agent. Multi-agent is the specialized tool you reach for when a context boundary, a parallelization opportunity, or a genuine specialization need makes it worth several times the cost.

---

## What's Next

This is the final pattern in the series. Across eleven posts we've gone from a [basic reasoning agent](https://github.com/aws-samples/sample-basic-reasoning-agents/blob/main/Building%20Basic%20Reasoning%20Agents%20with%20Amazon%20Bedrock%20and%20Strands%20SDK.md) to tools, servers, computer use, coding, voice, orchestration, memory, simulation, observation, and now collaboration. A few threads run through all of them: **patterns combine**: a real system often blends several patterns. **Agent design is contextual**: choose patterns by interaction surface, task complexity, latency tolerance, and constraints. Finally, **start simple**: reach for the least complex pattern that solves the problem, and add capability only when the problem demands it.

The natural next step is to build. The **[companion sample](README.md)** implements swarm handoff, agents-as-tools, and debate.

---

## Resources

- [Companion sample: Multi-Agent Collaboration](README.md)
- [AWS Prescriptive Guidance - Multi-agent collaboration](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-patterns/multi-agent-collaboration.html)
- [Anthropic: Building multi-agent systems — when and how](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them)
- [Strands multi-agent documentation](https://strandsagents.com/docs/user-guide/sdk/multi-agent/swarm/)
- [Amazon Bedrock User Guide](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html)

---

**Tim Sitze** is a Solutions Architect at Amazon Web Services, where he works with cybersecurity ISVs to design and scale their products on AWS. He specializes in security, AI/ML, IoT and data platform architectures, and has partnered on workloads spanning identity threat intelligence, agentic AI, and cloud-native security operations. Tim is based in the Washington, D.C. area.  
