"""
Seed de snapshots de test pour le worker.

Objectif :
- Partir de quelques snapshots existants en base
- Les marquer comme "baseline" (extracted_json rempli)
- Créer pour chacun un nouveau snapshot modifié (jobs, pricing, tools, etc.)
- Laisser le worker traiter ces nouveaux snapshots pour vérifier la détection de signaux
"""

import asyncio
import hashlib
import json
import random
import uuid
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text

from config import config


def _make_engine():
  # Utilise le même pattern que main.py (asyncpg)
  db_url = config.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
  return create_async_engine(db_url, echo=False)


SCENARIOS = [
    "jobs_intensity",      # Ajout de 'activement' / 'urgemment' sur une page déjà jobs
    "new_jobs_block",      # Ajout d'un bloc complet de recrutement
    "add_pricing_section", # Ajout d'une section pricing avec prix explicites
    "add_tool_intercom",   # Ajout d'un script Intercom
    "funding_announcement",# Ajout d'un texte de levée de fonds
    "partnership_announcement",  # Ajout d'un texte de partenariat
    "expansion_announcement",    # Ajout d'un texte d'expansion géographique
]


def apply_scenario(html: str, scenario: str) -> str:
    """Retourne une version modifiée du HTML selon un scénario."""
    if not html:
        html = ""

    marker = f"<!-- seed_scenario:{scenario} -->"

    if scenario == "jobs_intensity":
        snippet = """
        <section id="careers">
          <h2>Carrières</h2>
          <p>Nous recrutons <strong>activement</strong> des développeurs backend pour accélérer notre croissance.</p>
        </section>
        """
        return html + "\n" + snippet + marker

    if scenario == "new_jobs_block":
        snippet = """
        <section id="jobs">
          <h2>Nous recrutons</h2>
          <p>Nous recrutons plusieurs profils : développeurs, sales et customer success.</p>
          <ul>
            <li>CDI - Développeur backend</li>
            <li>CDI - Sales B2B</li>
            <li>CDI - Customer Success Manager</li>
          </ul>
        </section>
        """
        return html + "\n" + snippet + marker

    if scenario == "add_pricing_section":
        snippet = """
        <section id="pricing">
          <h2>Nos tarifs</h2>
          <div class="plan">
            <h3>Plan Starter</h3>
            <p>49 € / mois</p>
          </div>
          <div class="plan">
            <h3>Plan Pro</h3>
            <p>99 € / mois</p>
          </div>
        </section>
        """
        return html + "\n" + snippet + marker

    if scenario == "add_tool_intercom":
        snippet = """
        <script src="https://widget.intercom.io/widget/abc123"></script>
        """
        return html + "\n" + snippet + marker

    if scenario == "funding_announcement":
        snippet = """
        <section id="funding">
          <h2>Levée de fonds</h2>
          <p>Nous sommes fiers d'annoncer une nouvelle levée de fonds de 5M€ en série A
          pour accélérer notre expansion européenne.</p>
        </section>
        """
        return html + "\n" + snippet + marker

    if scenario == "partnership_announcement":
        snippet = """
        <section id="partners">
          <h2>Nouveau partenariat stratégique</h2>
          <p>Nous avons conclu un partenariat stratégique avec ACME Corp pour
          renforcer notre offre auprès des ETI.</p>
        </section>
        """
        return html + "\n" + snippet + marker

    if scenario == "expansion_announcement":
        snippet = """
        <section id="expansion">
          <h2>Ouverture d'un nouveau bureau</h2>
          <p>Nous ouvrons un nouveau bureau à Berlin pour soutenir notre expansion en Europe.</p>
        </section>
        """
        return html + "\n" + snippet + marker

    # Fallback: pas de modif
    return html + "\n" + marker


async def seed_test_snapshots(limit: int = 10):
    engine = _make_engine()
    async with AsyncSession(engine) as session:
        # On prend quelques snapshots existants, idéalement avec du HTML
        result = await session.execute(
            text(
                """
                SELECT id, domain_id, url, fetched_at, status_code, hash, html_text, extracted_json
                FROM domain_snapshots
                WHERE html_text IS NOT NULL
                ORDER BY fetched_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
        rows = result.mappings().all()

        if not rows:
            print("Aucun snapshot existant trouvé en base, rien à dupliquer.")
            return

        print(f"Trouvé {len(rows)} snapshots existants. Création de versions modifiées pour tests...")

        for idx, row in enumerate(rows):
            original_id = row["id"]
            domain_id = row["domain_id"]
            url = row["url"]
            status_code = row["status_code"] or 200
            html = row["html_text"] or ""

            # 1) Marquer le snapshot existant comme baseline si pas encore traité
            if row["extracted_json"] is None:
                baseline_json = {
                    "processed": True,
                    "processed_at": datetime.utcnow().isoformat(),
                    "content_changed": False,
                    "is_first_snapshot": True,
                    "reason": "seed_test_baseline",
                }
                await session.execute(
                    text(
                        """
                        UPDATE domain_snapshots
                        SET extracted_json = :extracted_json
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": original_id,
                        "extracted_json": json.dumps(baseline_json),
                    },
                )

            # 2) Choisir un scénario en tournant sur la liste
            scenario = SCENARIOS[idx % len(SCENARIOS)]

            new_html = apply_scenario(html, scenario)
            new_hash = hashlib.sha256(new_html.encode("utf-8")).hexdigest()

            new_id = str(uuid.uuid4())

            await session.execute(
                text(
                    """
                    INSERT INTO domain_snapshots (
                        id,
                        domain_id,
                        url,
                        fetched_at,
                        status_code,
                        hash,
                        html_text,
                        extracted_json,
                        created_at,
                        updated_at
                    ) VALUES (
                        :id,
                        :domain_id,
                        :url,
                        :fetched_at,
                        :status_code,
                        :hash,
                        :html_text,
                        NULL,
                        :created_at,
                        :updated_at
                    )
                    """
                ),
                {
                    "id": new_id,
                    "domain_id": domain_id,
                    "url": url,
                    "fetched_at": datetime.utcnow() + timedelta(minutes=idx + 1),
                    "status_code": status_code,
                    "hash": new_hash,
                    "html_text": new_html,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                },
            )

            print(f"- Snapshot seedé pour {url} avec scénario '{scenario}' (nouvel id: {new_id})")

        await session.commit()
        print("Seed terminé. Tu peux maintenant lancer le worker pour traiter ces nouveaux snapshots.")


if __name__ == "__main__":
    asyncio.run(seed_test_snapshots(limit=10))

