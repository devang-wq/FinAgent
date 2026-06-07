"""Curated evaluation test cases for FinAgent compliance queries.

Each case has:
  question   — the compliance query sent to the agent
  reference  — optional ground-truth (used by RAGAS ContextRecall / Precision)
  tags       — topic labels for filtering eval runs
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalCase:
    question: str
    reference: str = ""
    tags: list[str] = field(default_factory=list)


EVAL_CASES: list[EvalCase] = [
    # ── Sanctions ─────────────────────────────────────────────────────────
    EvalCase(
        question="Is Roman Abramovich subject to any international sanctions? Which jurisdictions?",
        reference=(
            "Roman Abramovich is sanctioned by the UK (OFSI), EU, and other Western "
            "jurisdictions following the 2022 Russia-Ukraine conflict, with asset freezes "
            "and travel bans."
        ),
        tags=["sanctions", "russia"],
    ),
    EvalCase(
        question="What is Oleg Deripaska's sanctions status and what companies is he associated with?",
        tags=["sanctions", "russia", "graph"],
    ),
    EvalCase(
        question="List the primary relationship types used to connect sanctioned Russian entities in the dataset.",
        tags=["sanctions", "graph", "schema"],
    ),
    EvalCase(
        question="Which entities from North Korea appear in the OpenSanctions dataset?",
        tags=["sanctions", "north_korea"],
    ),
    # ── PEP / AML ─────────────────────────────────────────────────────────
    EvalCase(
        question=(
            "What are the defining characteristics of a politically exposed person (PEP) "
            "and what AML risks do they present?"
        ),
        reference=(
            "PEPs are individuals holding or having held prominent public positions. "
            "Risks include bribery, corruption, and laundering of misappropriated public funds. "
            "Enhanced due diligence is required under FATF guidance."
        ),
        tags=["pep", "aml"],
    ),
    EvalCase(
        question=(
            "How should a compliance officer handle a payment from a PEP in a "
            "high-risk jurisdiction according to FATF guidelines?"
        ),
        tags=["pep", "aml", "compliance"],
    ),
    EvalCase(
        question="What is the difference between a domestic PEP and a foreign PEP for AML purposes?",
        tags=["pep", "aml"],
    ),
    # ── Offshore / ICIJ ───────────────────────────────────────────────────
    EvalCase(
        question="What types of offshore structures appear most frequently in the Panama Papers data?",
        tags=["icij", "offshore"],
    ),
    EvalCase(
        question=(
            "Which jurisdictions are most commonly used for shell company formation "
            "according to the ICIJ Offshore Leaks database?"
        ),
        tags=["icij", "offshore"],
    ),
    # ── SEC ───────────────────────────────────────────────────────────────
    EvalCase(
        question="Summarise recent SEC enforcement actions related to OFAC sanctions violations.",
        tags=["sec", "ofac", "enforcement"],
    ),
    EvalCase(
        question=(
            "What disclosures have public companies made regarding beneficial ownership "
            "risk in recent 10-K filings?"
        ),
        tags=["sec", "beneficial_ownership"],
    ),
    # ── Court ─────────────────────────────────────────────────────────────
    EvalCase(
        question="What legal precedents exist in US courts for prosecuting trade-based money laundering?",
        tags=["court", "aml", "tbml"],
    ),
    EvalCase(
        question=(
            "Describe the elements prosecutors must prove in a wire fraud case involving "
            "offshore accounts, citing relevant case law."
        ),
        tags=["court", "wire_fraud"],
    ),
    # ── Procurement ───────────────────────────────────────────────────────
    EvalCase(
        question=(
            "Which federal agencies have awarded the largest cybersecurity intelligence "
            "contracts, and to whom?"
        ),
        tags=["procurement", "cybersecurity"],
    ),
    # ── Hallucination traps (no relevant data expected in corpus) ─────────
    EvalCase(
        question="What is Apple's current stock price?",
        reference="",
        tags=["hallucination_trap"],
    ),
    EvalCase(
        question="Describe FinAgent's internal database schema in detail.",
        reference="",
        tags=["hallucination_trap"],
    ),
    EvalCase(
        question="Who won the most recent FIFA World Cup?",
        reference="",
        tags=["hallucination_trap"],
    ),
]
