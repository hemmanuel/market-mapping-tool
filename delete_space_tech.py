import asyncio
from src.db.neo4j_session import driver

async def delete_graph(pipeline_id: str):
    print(f'Deleting graph data for pipeline: {pipeline_id}')
    async with driver.session() as session:
        await session.run(
            f'''
            MATCH (n) WHERE n.pipeline_id = "{pipeline_id}"
            DETACH DELETE n
            '''
        )
        print('Deleted nodes and relationships.')
    print('Deletion complete.')

if __name__ == '__main__':
    asyncio.run(delete_graph('771ccbbd-8f44-44c7-bb9e-b008bbb91c8b'))