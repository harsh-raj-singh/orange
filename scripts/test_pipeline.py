import asyncio
import json
import os

import chromadb
from neo4j import GraphDatabase
from core.agents.issue_agent.runner import run_issue_agent
from core.agents.solution_agent.runner import run_solution_agent
from core.graph_schema_v2 import ConversationType, Session, SourceType
from core.graph_upsert.dedup import ORANGE_NODE_VECTOR_COLLECTION
from core.graph_upsert.writer import GraphUpsertEngine

try:
    from dotenv import load_dotenv
except Exception:  # noqa: BLE001
    load_dotenv = None


def _resolve_neo4j_uri() -> str:
    explicit = (os.getenv("NEO4J_URL") or os.getenv("MEMGRAPH_URL") or "").strip()
    if explicit:
        return explicit

    scheme = (os.getenv("MEMGRAPH_SCHEME") or "bolt").strip()
    host = (os.getenv("MEMGRAPH_HOST") or "").strip()
    port = (os.getenv("MEMGRAPH_PORT") or "7687").strip()

    if host:
        return f"{scheme}://{host}:{port}"
    return "bolt://localhost:7687"


def _resolve_neo4j_auth() -> tuple[str, str] | None:
    username = (os.getenv("NEO4J_USERNAME") or os.getenv("MEMGRAPH_USERNAME") or "").strip()
    password = (os.getenv("NEO4J_PASSWORD") or os.getenv("MEMGRAPH_PASSWORD") or "").strip()
    if username and password:
        return username, password
    return None


TRANSCRIPT = """
Turn 1 [user]: Getting this error in my NestJS app:
ERROR [ExceptionHandler] TypeError: Cannot read properties of undefined (reading 'id')
    at UserService.findById (src/services/user.service.ts:34:28)
async findById(id: string): Promise<User> {
    const user = await this.userRepository.findOne({ where: { id } });
    return user.profile.id;
}

Turn 2 [assistant]: The issue is that findOne can return null. Add a null check:
async findById(id: string): Promise<User> {
    const user = await this.userRepository.findOne({ where: { id } });
    if (!user) throw new NotFoundException(`User ${id} not found`);
    return user;
}

Turn 3 [user]: Applied that fix. Now getting:
TS2339: Property 'profile' does not exist on type 'User'
@Entity()
export class User {
    @PrimaryGeneratedColumn('uuid')
    id: string;
    @Column()
    email: string;
}

Turn 4 [assistant]: Add the relation decorator to your User entity:
@OneToOne(() => Profile, profile => profile.user, { eager: true })
@JoinColumn()
profile: Profile;

Turn 5 [user]: That fixed the relation error but now TypeORM throws:
QueryFailedError: relation "profiles" does not exist
Do I need to run migrations?
"""


async def main():
    if load_dotenv is not None:
        load_dotenv()

    print("=== SOLUTION AGENT OUTPUT ===")
    solution_output = await run_solution_agent("test-001", TRANSCRIPT)
    print(json.dumps(solution_output.model_dump(), indent=2, default=str))

    print("\n=== ISSUE AGENT OUTPUT ===")
    issue_output = await run_issue_agent("test-001", TRANSCRIPT, solution_output)
    print(json.dumps(issue_output.model_dump(), indent=2, default=str))

    # === UPSERT TO NEO4J + CHROMA ===
    print("\n=== UPSERT V2 ===")

    neo4j_uri = _resolve_neo4j_uri()
    neo4j_auth = _resolve_neo4j_auth()
    if neo4j_auth:
        neo4j_client = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    else:
        neo4j_client = GraphDatabase.driver(neo4j_uri)
    chroma_client = chromadb.PersistentClient(path=os.getenv("CHROMA_PATH", "./chroma_db"))

    engine = GraphUpsertEngine(neo4j=neo4j_client, chroma=chroma_client)

    session = Session(
        node_id="session_test-001",
        source=SourceType.STREAMLIT,
        conversation_type=ConversationType.DEBUGGING,
        title="Test NestJS Debugging Session",
        summary="Debugging TypeScript errors in NestJS UserService",
    )

    summary = engine.upsert_v2(
        session=session,
        user_id="test-user",
        issue_output=issue_output,
        solution_output=solution_output,
    )

    print(summary)

    collection = chroma_client.get_collection(ORANGE_NODE_VECTOR_COLLECTION)
    results = collection.peek(5)
    embeddings = results.get("embeddings") if isinstance(results, dict) else None
    print("Chroma IDs:", results.get("ids") if isinstance(results, dict) else [])
    print("Embedding dims:", len(embeddings[0]) if embeddings else "NO EMBEDDINGS")

    neo4j_client.close()


asyncio.run(main())
