import asyncio
import csv
import os
from neo4j import AsyncGraphDatabase

URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

async def export_data():
    driver = AsyncGraphDatabase.driver(URI, auth=(USER, PASSWORD))
    async with driver.session() as session:
        print("Exporting nodes to nodes.csv...")
        nodes_res = await session.run("MATCH (c:CanonicalEntity) RETURN id(c) AS Id, c.name AS Label, c.type AS EntityType")
        
        with open("nodes.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Id", "Label", "EntityType"])
            async for record in nodes_res:
                writer.writerow([record["Id"], record["Label"], record["EntityType"]])
        
        print("Exporting edges to edges.csv (this aggregates relationships into weights)...")
        edges_res = await session.run("""
            MATCH (cs:CanonicalEntity)<-[:RESOLVES_TO]-(rs:RawEntity)-[r:RAW_RELATIONSHIP]->(rt:RawEntity)-[:RESOLVES_TO]->(ct:CanonicalEntity)
            WITH id(cs) AS Source, id(ct) AS Target, r.type AS Label, count(r) as Weight
            RETURN Source, Target, 'Directed' AS Type, Label, Weight
        """)
        
        with open("edges.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Source", "Target", "Type", "Label", "Weight"])
            async for record in edges_res:
                writer.writerow([record["Source"], record["Target"], record["Type"], record["Label"], record["Weight"]])
                
    await driver.close()
    print("Done! You can now import nodes.csv and edges.csv into Gephi.")

if __name__ == "__main__":
    asyncio.run(export_data())
