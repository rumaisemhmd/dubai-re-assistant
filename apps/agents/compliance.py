"""Compliance-checker agent: does a proposed deal/scenario violate RERA rules?

Retrieval finds the RERA/DLD regulation text relevant to the scenario (via
RetrievalAgent, i.e. Gemini embeddings over ingested Document/DocumentChunk
rows); Gemini then reasons over exactly that retrieved text to produce a
verdict. The model is constrained to a JSON schema (response_json_schema)
that requires structured citations tied to specific retrieved sources,
rather than free-text prose, so every claim traces back to a specific
document/chunk and (per the model's reading of that chunk) the specific
article or clause it's grounded in — never a bare yes/no answer.

If retrieval finds nothing relevant, no LLM call is made and the verdict is
"unclear" with an explanation, rather than letting the model guess ungrounded.
"""
import hashlib
import json
import time
from dataclasses import dataclass, field

from django.conf import settings
from django.core.cache import cache
from google import genai
from google.genai import errors, types

from apps.agents.retrieval import RetrievalAgent

DEFAULT_TOP_K = 8
# Free-tier Gemini reasoning model — see apps.ingestion.embeddings for the
# same rationale on why this project targets Gemini over a paid provider.
# Deliberately Gemini-only for now (no Anthropic API credits available).
# The reasoning call is isolated to get_client()/_generate_with_retry()/this
# constant, so swapping in Claude (settings.ANTHROPIC_API_KEY + anthropic
# SDK) later is a localized change, not a rewrite of the agent's logic.
# gemini-3.6-flash's free-tier daily quota (20 requests/day) was getting
# exhausted during dashboard testing. gemini-2.5-flash (and gemini-2.5-flash-lite)
# are NOT viable alternatives — this project's API key gets a hard 404 "no
# longer available to new users" on both, regardless of remaining quota.
# gemini-3.1-flash-lite works and, as a lite variant, carries a materially
# higher free-tier daily quota than the full flash models.
DEFAULT_MODEL = "gemini-3.1-flash-lite"

# Cache identical scenario checks so repeatedly testing the same input
# doesn't burn free-tier daily quota on a fresh Gemini call every time. Keyed
# on the exact scenario text + top_k + model, so anything that could change
# the result invalidates the cache entry.
CACHE_TIMEOUT_SECONDS = 60 * 60 * 24
# This call sits in the request path of the dashboard's "Run Analysis" button —
# unlike the batch ingestion pipeline's long backoff, a user is watching a
# spinner, so retries here are few and short: retry on 429 (rate limit) and
# 503 (transient overload) only, not on other errors.
_MAX_RETRIES = 3
_RETRY_BACKOFF_SECONDS = 2
_RETRYABLE_CODES = {429, 503}

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["violation", "compliant", "unclear"],
            "description": (
                "'violation' if the scenario clearly breaches one or more cited rules, "
                "'compliant' if it clearly satisfies them, 'unclear' if the excerpts don't "
                "give enough information to say either way."
            ),
        },
        "summary": {
            "type": "string",
            "description": "Plain-language explanation of the verdict, in 2-4 sentences.",
        },
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_number": {
                        "type": "integer",
                        "description": "The [N] label of the source excerpt this citation refers to.",
                    },
                    "article_or_rule": {
                        "type": "string",
                        "description": (
                            "The specific article, clause, or rule number/name as stated in the "
                            "source text (e.g. 'Article 7', 'Law No. 8 of 2007, Article 3'). "
                            "Use 'unspecified' if the excerpt doesn't name one explicitly."
                        ),
                    },
                    "relevance": {
                        "type": "string",
                        "description": "One sentence on how this article/rule supports the verdict.",
                    },
                },
                "required": ["source_number", "article_or_rule", "relevance"],
            },
        },
    },
    "required": ["verdict", "summary", "citations"],
}

SYSTEM_PROMPT = (
    "You are a Dubai real estate compliance analyst. You are given a proposed deal or "
    "scenario and a numbered list of excerpts retrieved from RERA/DLD regulations. "
    "Determine whether the scenario violates, complies with, or is unclear under those "
    "excerpts, using ONLY the provided excerpts as your basis — do not rely on outside "
    "knowledge of UAE law beyond what's in the excerpts, and do not invent article numbers "
    "that aren't in the text. Some excerpts may be in Arabic; read them directly and cite "
    "their article/circular reference as stated. If the excerpts are insufficient to reach "
    "a confident verdict, say so with verdict='unclear' rather than guessing. Respond with "
    "at least one citation for every excerpt your verdict relies on."
)


@dataclass
class Citation:
    source_number: int
    article_or_rule: str
    relevance: str
    document_title: str
    chunk_id: int
    similarity: float
    excerpt: str


@dataclass
class ComplianceAssessment:
    scenario: str
    verdict: str  # "violation" | "compliant" | "unclear"
    summary: str
    citations: list[Citation] = field(default_factory=list)
    sources_considered: int = 0


_client = None


def get_client():
    global _client
    if _client is None:
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set — required for the compliance agent.")
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


def _generate_with_retry(client, model, prompt, config):
    """Call generate_content, retrying on 429 (rate limit) and 503 (transient
    overload) with a short backoff — see _MAX_RETRIES/_RETRY_BACKOFF_SECONDS.
    """
    for attempt in range(_MAX_RETRIES):
        try:
            return client.models.generate_content(model=model, contents=prompt, config=config)
        except errors.APIError as exc:
            if exc.code not in _RETRYABLE_CODES or attempt == _MAX_RETRIES - 1:
                raise
            time.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))


def _build_prompt(scenario, chunks):
    sources = []
    for i, chunk in enumerate(chunks, start=1):
        sources.append(
            f"[{i}] Source: \"{chunk.document_title}\" (language={chunk.language})\n{chunk.content}"
        )
    sources_block = "\n\n".join(sources)
    return (
        f"Proposed scenario:\n{scenario}\n\n"
        f"Retrieved regulation excerpts:\n\n{sources_block}"
    )


class ComplianceAgent:
    """Flags whether a scenario violates RERA rules, citing the specific article/rule."""

    def __init__(self, retrieval_agent=None, top_k=DEFAULT_TOP_K, model=None):
        self.retrieval_agent = retrieval_agent or RetrievalAgent(top_k=top_k)
        self.top_k = top_k
        self.model = model or DEFAULT_MODEL

    def check(self, scenario):
        scenario = (scenario or "").strip()
        if not scenario:
            raise ValueError("scenario must be non-empty.")

        cache_key = self._cache_key(scenario)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        assessment = self._check_uncached(scenario)
        cache.set(cache_key, assessment, timeout=CACHE_TIMEOUT_SECONDS)
        return assessment

    def _cache_key(self, scenario):
        digest = hashlib.sha256(scenario.encode("utf-8")).hexdigest()
        return f"compliance:v1:{self.model}:{self.top_k}:{digest}"

    def _check_uncached(self, scenario):
        chunks = self.retrieval_agent.retrieve(scenario, top_k=self.top_k)
        if not chunks:
            return ComplianceAssessment(
                scenario=scenario,
                verdict="unclear",
                summary=(
                    "No relevant RERA/DLD regulation text was found in the ingested "
                    "knowledge base for this scenario, so compliance cannot be assessed."
                ),
                citations=[],
                sources_considered=0,
            )

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_json_schema=REPORT_SCHEMA,
            temperature=0,
        )
        response = _generate_with_retry(
            get_client(), self.model, _build_prompt(scenario, chunks), config
        )
        result = json.loads(response.text)

        citations = []
        for c in result.get("citations", []):
            source_number = c.get("source_number")
            if not isinstance(source_number, int) or not (1 <= source_number <= len(chunks)):
                continue  # Model cited a source number that doesn't exist — drop rather than mislabel.
            chunk = chunks[source_number - 1]
            citations.append(
                Citation(
                    source_number=source_number,
                    article_or_rule=c.get("article_or_rule", "unspecified"),
                    relevance=c.get("relevance", ""),
                    document_title=chunk.document_title,
                    chunk_id=chunk.chunk_id,
                    similarity=chunk.similarity,
                    excerpt=chunk.content,
                )
            )

        return ComplianceAssessment(
            scenario=scenario,
            verdict=result.get("verdict", "unclear"),
            summary=result.get("summary", ""),
            citations=citations,
            sources_considered=len(chunks),
        )


def check_compliance(scenario, top_k=DEFAULT_TOP_K):
    """Module-level convenience wrapper around ComplianceAgent().check()."""
    return ComplianceAgent(top_k=top_k).check(scenario)
