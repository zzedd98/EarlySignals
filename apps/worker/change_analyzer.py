"""
Change analyzer - Compare snapshots to detect meaningful changes
"""
import re
from typing import Dict, List, Set, Tuple
from difflib import SequenceMatcher
from html.parser import HTMLParser
from html import unescape

# Limite de texte analysé (SequenceMatcher est O(n²) — pages énormes = freeze).
MAX_ANALYSIS_CHARS = 80_000
MAX_SEGMENT_COMPARE = 120


def _clip_text(text: str, limit: int = MAX_ANALYSIS_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit]


class TextExtractor(HTMLParser):
    """Extract visible text from HTML"""
    
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.skip_tags = {'script', 'style', 'meta', 'link', 'head', 'noscript'}
        self.current_tag = None
    
    def handle_starttag(self, tag, attrs):
        self.current_tag = tag.lower()
    
    def handle_endtag(self, tag):
        self.current_tag = None
    
    def handle_data(self, data):
        if self.current_tag not in self.skip_tags:
            cleaned = data.strip()
            if cleaned and len(cleaned) > 2:  # Ignore very short fragments
                self.text_parts.append(cleaned)


def extract_text_from_html(html: str) -> str:
    """Extract visible text content from HTML"""
    if not html:
        return ""
    
    # Remove script and style tags completely
    html = re.sub(r'<script[^>]*>[\s\S]*?</script>', '', html, flags=re.IGNORECASE)
    html = re.sub(r'<style[^>]*>[\s\S]*?</style>', '', html, flags=re.IGNORECASE)
    
    # Extract text using parser
    parser = TextExtractor()
    parser.feed(html)
    
    # Join and normalize whitespace
    text = ' '.join(parser.text_parts)
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def extract_keywords(text: str, keywords: List[str]) -> Set[str]:
    """Extract which keywords are present in the text"""
    text_lower = text.lower()
    found = set()
    for keyword in keywords:
        if keyword.lower() in text_lower:
            found.add(keyword.lower())
    return found


def calculate_text_similarity(text1: str, text2: str) -> float:
    """Calculate similarity ratio between two texts (0.0 to 1.0)"""
    if not text1 and not text2:
        return 1.0
    if not text1 or not text2:
        return 0.0
    
    # Use SequenceMatcher for similarity
    return SequenceMatcher(None, text1, text2).ratio()


def extract_added_text(old_text: str, new_text: str) -> str:
    """
    Extract text that was added in the new version.
    Returns the new text segments that don't appear in old text.
    """
    if not old_text:
        return new_text  # Everything is new
    
    if not new_text:
        return ""
    
    # Split into sentences/segments
    old_segments = re.split(r'[.!?]\s+', old_text)
    new_segments = re.split(r'[.!?]\s+', new_text)
    old_segments = old_segments[:MAX_SEGMENT_COMPARE]
    new_segments = new_segments[:MAX_SEGMENT_COMPARE]
    
    # Find segments that are new
    old_lower = old_text.lower()
    added_segments = []
    
    for segment in new_segments:
        segment_clean = segment.strip()
        if not segment_clean:
            continue
        
        # Check if this segment (or similar) exists in old text
        segment_lower = segment_clean.lower()
        
        # Check exact match
        if segment_lower in old_lower:
            continue
        
        # Check if it's a significant addition (not just a word variation)
        # If segment is > 20 chars and not found, it's likely new content
        if len(segment_clean) > 20:
            # Check for fuzzy match (similarity > 0.8 means it's probably a reformulation)
            best_match_ratio = 0.0
            for old_seg in old_segments:
                if len(old_seg.strip()) > 10:
                    ratio = SequenceMatcher(None, segment_lower, old_seg.lower()).ratio()
                    best_match_ratio = max(best_match_ratio, ratio)
            
            if best_match_ratio < 0.7:  # Less than 70% similar = new content
                added_segments.append(segment_clean)
        elif len(segment_clean) > 10:
            # Shorter segments: check if it contains new keywords
            added_segments.append(segment_clean)
    
    return ' '.join(added_segments)


def extract_removed_text(old_text: str, new_text: str) -> str:
    """Extract text that was removed from the old version"""
    return extract_added_text(new_text, old_text)  # Reverse the comparison


# --- Price extraction helpers -------------------------------------------------

# Match common price formats: "49 €", "49€", "49.90 EUR", "$29", "29 USD", etc.
PRICE_REGEX = re.compile(
    r"""(?:
        (?:€|\$|£)\s*\d[\d\s.,]*   # €49, € 49.90, $29
        |
        \d[\d\s.,]*\s*(?:€|eur|euros?|usd|dollars?)  # 49 €, 49 eur, 49 dollars
    )""",
    re.IGNORECASE | re.VERBOSE,
)


def _parse_price_value(token: str) -> float | None:
    """Convert a price token to a numeric value (best-effort)."""
    # Remove currency symbols and words
    cleaned = re.sub(r'[^\d,.\s]', '', token)
    cleaned = cleaned.strip()
    if not cleaned:
        return None

    # Remove spaces inside number (e.g. "1 299" -> "1299")
    cleaned = cleaned.replace(" ", "")

    # Handle comma/point as decimal/thousands separators
    # Heuristic: if both '.' and ',' present, assume '.' thousands, ',' decimal (EU style)
    if ',' in cleaned and '.' in cleaned:
        if cleaned.find('.') < cleaned.find(','):
            # "1.299,99" -> "1299.99"
            cleaned = cleaned.replace('.', '').replace(',', '.')
        else:
            # "1,299.99" -> "1299.99"
            cleaned = cleaned.replace(',', '')
    else:
        # If only comma, treat as decimal separator
        if ',' in cleaned and '.' not in cleaned:
            cleaned = cleaned.replace(',', '.')
        # If only dot, keep as is

    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_price_values(text: str) -> List[float]:
    """Extract numeric price values from text."""
    prices: List[float] = []
    for match in PRICE_REGEX.findall(text):
        value = _parse_price_value(match)
        if value is not None:
            prices.append(value)
    return prices


def analyze_price_changes(old_text: str, new_text: str) -> Dict:
    """
    Analyze price changes between two texts.

    Returns:
        {
            "has_price_change": bool,
            "old_prices": List[float],
            "new_prices": List[float],
            "max_increase": float,
            "max_decrease": float,
        }
    """
    old_prices = extract_price_values(old_text)
    new_prices = extract_price_values(new_text)

    # Quick check: if price sets are identical, no change
    old_sorted = sorted(old_prices)
    new_sorted = sorted(new_prices)
    has_price_change = old_sorted != new_sorted

    max_increase = 0.0
    max_decrease = 0.0

    if has_price_change and old_prices and new_prices:
        # Compare sorted lists pairwise (best-effort; we don't know exact mapping)
        length = min(len(old_sorted), len(new_sorted))
        for i in range(length):
            delta = new_sorted[i] - old_sorted[i]
            if delta > max_increase:
                max_increase = delta
            if delta < max_decrease:
                max_decrease = delta

    return {
        "has_price_change": has_price_change,
        "old_prices": old_prices,
        "new_prices": new_prices,
        "max_increase": max_increase,
        "max_decrease": max_decrease,
    }


class ChangeAnalyzer:
    """Analyze changes between two snapshots to determine if they're significant"""
    
    # Minimum similarity threshold to consider content "unchanged"
    MIN_SIMILARITY_THRESHOLD = 0.85  # 85% similar = minor change
    
    # Minimum length of added/removed text to be considered significant
    MIN_CHANGE_LENGTH = 50  # characters
    
    def __init__(self):
        pass
    
    def analyze(self, old_html: str, new_html: str) -> Dict:
        """
        Analyze changes between old and new HTML snapshots.
        
        Returns:
            {
                "similarity": float,  # 0.0 to 1.0
                "is_significant": bool,  # True if change is meaningful
                "added_text": str,  # New text content
                "removed_text": str,  # Removed text content
                "change_type": str,  # "major", "minor", "none"
                "price_change": {...},  # Details about price changes
            }
        """
        # Extract text from both HTMLs
        old_text = _clip_text(extract_text_from_html(old_html or ""))
        new_text = _clip_text(extract_text_from_html(new_html or ""))
        
        # Calculate similarity
        similarity = calculate_text_similarity(old_text, new_text)
        
        # Extract added/removed text
        added_text = extract_added_text(old_text, new_text)
        removed_text = extract_removed_text(old_text, new_text)

        # Analyze price changes
        price_change_info = analyze_price_changes(old_text, new_text)
        
        # Determine if change is significant
        is_significant = self._is_significant_change(
            similarity,
            added_text,
            removed_text,
            old_text,
            new_text,
            price_change_info,
        )
        
        # Determine change type
        if similarity > self.MIN_SIMILARITY_THRESHOLD:
            change_type = "none" if similarity > 0.95 else "minor"
        else:
            change_type = "major"
        
        return {
            "similarity": similarity,
            "is_significant": is_significant,
            "added_text": added_text,
            "removed_text": removed_text,
            "change_type": change_type,
            "old_text_length": len(old_text),
            "new_text_length": len(new_text),
            "added_text_length": len(added_text),
            "removed_text_length": len(removed_text),
            "price_change": price_change_info,
            "has_price_change": price_change_info["has_price_change"],
        }
    
    def _is_significant_change(
        self,
        similarity: float,
        added_text: str,
        removed_text: str,
        old_text: str,
        new_text: str,
        price_change_info: Dict,
    ) -> bool:
        """
        Determine if a change is significant enough to warrant signal detection.
        
        A change is significant if:
        1. Similarity is below threshold (major structural change)
        2. Added/removed text is substantial (> MIN_CHANGE_LENGTH chars)
        3. New keywords appear that weren't there before (jobs, pricing, etc.)
        4. OR any price actually changed (even if text diff is tiny)
        """
        # Any price change is ALWAYS significant (pricing is critical)
        if price_change_info.get("has_price_change"):
            return True

        # Major structural change
        if similarity < self.MIN_SIMILARITY_THRESHOLD:
            return True
        
        # Substantial text addition/removal
        if len(added_text) > self.MIN_CHANGE_LENGTH or len(removed_text) > self.MIN_CHANGE_LENGTH:
            return True
        
        # Check for important keywords in added text
        important_keywords = [
            # Jobs
            "recrutement", "recruitment", "recrute", "recrutons", "nous recrutons",
            "on recrute", "rejoignez-nous", "embauche", "emploi", "carrière",
            "poste", "offre d'emploi", "candidature", "hiring", "jobs", "careers",
            "join us", "we are hiring", "open positions", "job opening",
            # Intensity / urgency (jobs)
            "activement", "urgemment", "immédiatement", "dès maintenant",
            "actively hiring", "urgently hiring", "immediately hiring",
            # Pricing
            "pricing", "tarif", "prix", "plan", "forfait", "abonnement",
            "subscription", "billing", "devis",
            # Products
            "nouveau produit", "new product", "nouvelle fonctionnalité", "new feature",
            "lancement", "launch", "lancé", "launched", "release", "released",
            # Partnerships
            "partenaire", "partenaires", "partenariat", "partner", "partners",
            "partnership", "collaboration",
            # Expansion
            "ouverture", "expansion", "nouveau bureau", "new office", "new location",
            # Funding
            "levée de fonds", "funding", "investissement", "investment",
            "série a", "series a", "seed round",
        ]
        
        added_lower = added_text.lower()
        for keyword in important_keywords:
            if keyword.lower() in added_lower:
                return True
        
        return False
