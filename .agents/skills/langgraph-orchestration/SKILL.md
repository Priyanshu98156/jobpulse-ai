---
name: langgraph-orchestration
description: >-
  LangGraph and LangChain multi-agent state graph orchestration, cyclic loops,
  tool routing, human-in-the-loop checkpoints, and multi-provider LLM failover.
---

# LangGraph & LLM Multi-Agent Orchestration

Use this skill when designing, implementing, or debugging LangGraph state graphs, cyclic agent loops, multi-model LLM failover, and structured output chains.

---

## 1. Core StateGraph Design Architecture

Every LangGraph agent must be defined with an explicit, strictly typed state schema:

```python
from typing import TypedDict, Annotated, Sequence
import operator
from langchain_core.messages import BaseMessage

class JobPulseAgentState(TypedDict):
    # Appends new messages into the message list
    messages: Annotated[Sequence[BaseMessage], operator.add]
    candidate_profile: dict
    job_details: dict
    eligibility_status: str  # eligible, needs_look, ineligible
    match_score: int
    cover_letter_draft: str
    canary_detected: list[str]
    iteration_count: int
```

---

## 2. Cyclic Graph Construction & Nodes

Construct graphs with distinct responsibility nodes and deterministic routing:

```python
from langgraph.graph import StateGraph, END

workflow = StateGraph(JobPulseAgentState)

# 1. Define Nodes
workflow.add_node("eligibility_checker", check_remote_eligibility)
workflow.add_node("honeypot_scanner", scan_and_strip_honeypots)
workflow.add_node("tailor_cover_letter", draft_tailored_letter)
workflow.add_node("human_review_gate", pause_for_candidate_review)

# 2. Define Entry Point & Directed Edges
workflow.set_entry_point("eligibility_checker")

# 3. Conditional Branching
def route_after_eligibility(state: JobPulseAgentState) -> str:
    if state["eligibility_status"] == "ineligible":
        return END
    return "honeypot_scanner"

workflow.add_conditional_edges(
    "eligibility_checker",
    route_after_eligibility,
    {
        END: END,
        "honeypot_scanner": "honeypot_scanner"
    }
)

workflow.add_edge("honeypot_scanner", "tailor_cover_letter")
workflow.add_edge("tailor_cover_letter", "human_review_gate")
workflow.add_edge("human_review_gate", END)

# Compile Graph with Memory Checkpointer
app_graph = workflow.compile(
    checkpointer=memory_saver,
    interrupt_before=["human_review_gate"]  # Human-in-the-loop interruption
)
```

---

## 3. Multi-Key Pool & Multi-Provider Failover

When orchestrating agent LLM calls, integrate with the multi-key pool service to guarantee zero rate-limit downtime:

1. **Round-Robin Provider Rotation**:
   * Rotate calls across Groq (`llama-3.3-70b`), OpenRouter, Google Gemini (`gemini-2.5-flash`), Mistral, and Cerebras.
2. **Deterministic Fallback**:
   * If a provider returns HTTP 429 (Rate Limit Exhausted), catch the exception, mark that key in temporary cooldown, and switch to the next healthy key in the pool.
3. **Structured Outputs**:
   Always enforce Pydantic structured output using `.with_structured_output(Schema)` to prevent JSON syntax hallucinations.

---

## 4. Human-In-The-Loop Checkpointing

* Use `interrupt_before=["submission_node"]` to pause execution state in the checkpointer.
* Resume the graph by passing `None` as the input once the candidate approves or modifies the draft state.
