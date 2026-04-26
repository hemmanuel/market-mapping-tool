import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Iterable

from src.orchestrator.core.graph_store import normalize_graph_name


_LEGAL_SUFFIX_RE = re.compile(
    r"\b("
    r"llc|l\.l\.c|lp|l\.p|llp|l\.l\.p|inc|incorporated|corp|corporation|co|company|"
    r"ltd|limited|plc|sa|ag|gmbh"
    r")\b\.?",
    re.IGNORECASE,
)
_NON_WORD_RE = re.compile(r"[^a-z0-9&]+")
_WHITESPACE_RE = re.compile(r"\s+")


def _contains_any(value: str, needles: Iterable[str]) -> bool:
    return any(needle in value for needle in needles)


def normalize_entity_name_for_resolution(name: str | None) -> str:
    """Build a conservative alias key for entity identity resolution."""
    if not name:
        return ""

    normalized = normalize_graph_name(name).replace("&", " and ")
    normalized = _LEGAL_SUFFIX_RE.sub(" ", normalized)
    normalized = _NON_WORD_RE.sub(" ", normalized)
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized


def names_are_close(left: str, right: str) -> bool:
    left_key = normalize_entity_name_for_resolution(left)
    right_key = normalize_entity_name_for_resolution(right)
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    if len(left_key) < 8 or len(right_key) < 8:
        return False
    return SequenceMatcher(None, left_key, right_key).ratio() >= 0.94


def normalize_entity_type(entity_type: str | None, name: str | None = None, description: str | None = None) -> str:
    raw = normalize_graph_name(entity_type)
    normalized_name = normalize_graph_name(name)
    context = normalize_graph_name(" ".join(value for value in [entity_type, name, description] if value))

    if _contains_any(
        context,
        [
            "private equity",
            "financial sponsor",
            "investment firm",
            "asset manager",
            "investment manager",
            "investment company",
            "venture capital",
            "family office",
            "hedge fund",
            "fund manager",
        ],
    ):
        return "Investor"

    if raw in {"investor", "fund", "funds", "capital provider"}:
        return "Investor"

    if raw in {"unknown", "entity", "organization", "organisation", "company", ""} and _contains_any(
        normalized_name,
        [
            " capital",
            "capital ",
            " equity",
            "equity ",
            " investment",
            "investments",
            " ventures",
            " venture ",
            " fund",
            "asset management",
            "warburg pincus",
            "riverstone",
            "blackstone",
            "apollo",
            "kkr",
            "encap",
            "ngp",
            "quantum energy partners",
            "tailwater",
            "carnelian",
            "post oak energy capital",
        ],
    ):
        return "Investor"

    if _contains_any(context, ["investment bank", "law firm", "legal advisor", "financial advisor", "advisor"]):
        return "ServiceProvider"

    if _contains_any(
        context,
        [
            "e&p",
            "exploration and production",
            "oil producer",
            "gas producer",
            "operator",
            "portfolio company",
            "upstream company",
        ],
    ):
        return "Company"

    if raw in {"company", "startup", "incumbent", "utility"}:
        return "Company" if raw in {"startup", "incumbent"} else entity_type or "Company"

    if _contains_any(context, ["basin", "play", "field", "acreage", "leasehold", "asset"]):
        return "Asset"

    if _contains_any(context, ["regulator", "agency", "commission", "government", "policy", "regulatory"]):
        return "RegulatoryBody"

    if _contains_any(context, ["executive", "founder", "ceo", "cfo", "partner", "person", "individual"]):
        return "Person"

    if not entity_type or raw in {"unknown", "entity", "organization", "organisation"}:
        return "Unknown"

    return entity_type.strip()


def normalize_relationship_type(relationship_type: str | None, exact_quote: str | None = None) -> str:
    context = normalize_graph_name(" ".join(value for value in [relationship_type, exact_quote] if value))

    if _contains_any(
        context,
        [
            "invested",
            "investment",
            "backed",
            "financed",
            "funded",
            "sponsored",
            "provided capital",
            "capital commitment",
            "equity commitment",
        ],
    ):
        return "INVESTED_IN"

    if _contains_any(context, ["acquired", "acquisition", "bought", "purchased", "merged", "buyout"]):
        return "ACQUIRED"

    if _contains_any(context, ["owns", "owned", "ownership", "controls", "controlled", "portfolio company"]):
        return "OWNS_OR_CONTROLS"

    if _contains_any(
        context,
        ["advised", "advisor", "represented", "counsel", "underwrote", "placement agent", "arranger"],
    ):
        return "ADVISED"

    if _contains_any(context, ["operates", "operator", "drills", "produces", "acreage", "basin", "play"]):
        return "OPERATES_IN"

    if _contains_any(context, ["partnered", "partnership", "joint venture", "collaborated"]):
        return "PARTNERED_WITH"

    if _contains_any(context, ["announced", "launched", "formed", "created"]):
        return "ANNOUNCED"

    raw = normalize_graph_name(relationship_type)
    if not raw:
        return "RELATED_TO"
    return re.sub(r"[^A-Z0-9]+", "_", raw.upper()).strip("_") or "RELATED_TO"


def choose_canonical_name(names: list[str]) -> str:
    counts = Counter(name.strip() for name in names if name and name.strip())
    if not counts:
        return "Unknown"

    def rank(item: tuple[str, int]) -> tuple[int, int, int, str]:
        name, count = item
        stripped = normalize_entity_name_for_resolution(name)
        has_suffix = int(stripped != normalize_graph_name(name))
        return (-count, has_suffix, len(name), name.lower())

    return sorted(counts.items(), key=rank)[0][0]
