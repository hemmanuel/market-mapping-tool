import asyncio
from src.db.neo4j_session import driver

async def main():
    async with driver.session() as s:
        res = await s.run("MATCH (c:CanonicalEntity {name: 'Fischer Block'}) RETURN c.type as type, c.stage_estimate as stage, c.vc_dossier_total_raised as raised, c.strategic_ai_survival_score as ai_score")
        records = await res.data()
        for r in records:
            print(f"Type: {r['type']}")
            print(f"Stage: {r['stage']}")
            print(f"Raised: {r['raised']}")
            print(f"AI Score: {r['ai_score']}")

asyncio.run(main())