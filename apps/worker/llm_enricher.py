"""LLM enrichment for opportunities"""

from typing import Dict

from app.models.signal import Signal
from app.models.domain import Domain

from config import config
from openai import OpenAI


class LLMEnricher:
    """Enrich opportunities with LLM"""

    def __init__(self):
        if config.LLM_API_KEY:
            self.client = OpenAI(api_key=config.LLM_API_KEY, timeout=30.0)
        else:
            self.client = None

    async def enrich(
        self,
        signal: Signal,
        domain: Domain,
        change_summary: str = "",
    ) -> Dict[str, str]:
        """Enrich signal with LLM-generated content"""
        if not self.client:
            return {
                "why_it_matters": change_summary or f"Signal détecté: {signal.type}",
                "suggested_approach": "Contactez l'entreprise pour en savoir plus.",
            }

        try:
            prompt = f"""
Tu es un expert en veille business B2B. Analyse ce signal et génère:

1. "Pourquoi c'est intéressant" (2-3 phrases en français, ton professionnel)
   — Reprends et enrichis le résumé factuel ci-dessous (ne le contredis pas).
2. "Angle d'approche suggéré" (1 phrase concrète pour un message outreach)

Signal: {signal.type}
Domaine: {domain.domain}
URL preuve: {signal.proof_url}
Changement détecté: {change_summary or "non précisé"}

Réponds en JSON: {{"why_it_matters": "...", "suggested_approach": "..."}}
"""

            response = self.client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=300,
            )

            content = response.choices[0].message.content
            # Try to parse JSON
            import json

            try:
                result = json.loads(content)
                return {
                    "why_it_matters": result.get("why_it_matters", ""),
                    "suggested_approach": result.get("suggested_approach", ""),
                }
            except:
                return {
                    "why_it_matters": (
                        content.split('"why_it_matters":')[1].split('"')[1]
                        if '"why_it_matters":' in content
                        else ""
                    ),
                    "suggested_approach": (
                        content.split('"suggested_approach":')[1].split('"')[1]
                        if '"suggested_approach":' in content
                        else ""
                    ),
                }
        except Exception as e:
            print(f"LLM enrichment error: {e}")
            return {
                "why_it_matters": change_summary
                or f"Signal {signal.type} détecté sur {domain.domain}",
                "suggested_approach": "Contactez l'entreprise pour explorer cette opportunité.",
            }
