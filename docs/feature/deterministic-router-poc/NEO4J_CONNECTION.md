# Querying the Production Knowledge Graph (Neo4j)

In production, Neo4j ports are bound only to `127.0.0.1` on the GCP VM and are not reachable from the public internet. Use an SSH tunnel to open Neo4j Browser from your local machine.

**Step 1 — Open the SSH tunnel**

Run this in a dedicated terminal and keep it open while you work:

```bash
gcloud compute ssh kitabim-prod --zone=us-south1-c -- \
  -L 7474:127.0.0.1:7474 \
  -L 7687:127.0.0.1:7687 \
  -N
```

This forwards two ports to your local machine:
- `localhost:7474` → Neo4j Browser (HTTP)
- `localhost:7687` → Neo4j Bolt (query protocol)

**Step 2 — Open Neo4j Browser**

Navigate to http://localhost:7474 in your browser.

**Step 3 — Connect**

Fill in the connection form:

| Field | Value |
|-------|-------|
| Connect URL | `bolt://localhost:7687` |
| Username | `neo4j` |
| Password | value of `NEO4J_PASSWORD` from the production `.env` |

Click **Connect**.

**Step 4 — Run Cypher queries**

```cypher
// Count all entities in the graph
MATCH (e:Entity) RETURN count(e);

// Browse entities with their types
MATCH (e:Entity) RETURN e.name, e.type LIMIT 50;

// Find all connections for a specific entity
MATCH (a:Entity {name: "your entity name"})-[r:RELATED_TO]-(b:Entity)
RETURN a.name, r.relation, b.name;

// Visualise a subgraph (keep LIMIT low — the full graph is large)
MATCH (a:Entity)-[r:RELATED_TO]->(b:Entity)
RETURN a, r, b LIMIT 100;
```

**Step 5 — Close the tunnel**

Press `Ctrl+C` in the terminal running the `gcloud` command.
