"""
Service 4: Fraud Graph Intelligence Service
Builds account-device-IP-merchant-email graph, runs connected-component
and hop-based scoring, identifies ring expansion, computes cluster risk.
Adapts DRA's networkx blast-radius into fraud-neighbor spread.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Any

import networkx as nx
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.models.graph import GraphEntityNode, GraphEntityEdge, FactGraphClusterScore
from src.models.audit import AuditEvent

logger = get_logger(__name__)


class FraudGraphService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._graph: Optional[nx.Graph] = None

    async def build_graph_from_db(self) -> nx.Graph:
        """Load full entity graph from Postgres into networkx."""
        G = nx.Graph()

        nodes_result = await self.db.execute(select(GraphEntityNode))
        for node in nodes_result.scalars():
            G.add_node(
                node.node_id,
                node_type=node.node_type,
                entity_ref=node.entity_ref,
                risk_score=float(node.risk_score or 0),
                attributes=node.attributes_json or {},
            )

        edges_result = await self.db.execute(select(GraphEntityEdge))
        for edge in edges_result.scalars():
            G.add_edge(
                edge.src_node_id,
                edge.dst_node_id,
                edge_type=edge.edge_type,
                weight=float(edge.weight or 1),
                attributes=edge.attributes_json or {},
            )

        self._graph = G
        logger.info("graph_loaded", node_count=G.number_of_nodes(), edge_count=G.number_of_edges())
        return G

    async def add_transaction_to_graph(
        self,
        account_id: int,
        device_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        email: Optional[str] = None,
        card_id: Optional[int] = None,
        merchant_id: Optional[int] = None,
    ):
        """Register transaction entities and their relationships in the graph."""
        now = datetime.now(timezone.utc)
        account_node = f"account:{account_id}"
        await self._upsert_node(account_node, "account", str(account_id), now)

        if device_id:
            device_node = f"device:{device_id}"
            await self._upsert_node(device_node, "device", device_id, now)
            await self._upsert_edge(account_node, device_node, "account_device", now)

        if ip_address:
            ip_node = f"ip:{ip_address}"
            await self._upsert_node(ip_node, "ip", ip_address, now)
            await self._upsert_edge(account_node, ip_node, "account_ip", now)
            if device_id:
                await self._upsert_edge(f"device:{device_id}", ip_node, "device_ip", now)

        if email:
            email_node = f"email:{email}"
            await self._upsert_node(email_node, "email", email, now)
            await self._upsert_edge(account_node, email_node, "account_email", now)

        if card_id:
            card_node = f"card:{card_id}"
            await self._upsert_node(card_node, "card", str(card_id), now)
            await self._upsert_edge(account_node, card_node, "account_card", now)

        if merchant_id:
            merchant_node = f"merchant:{merchant_id}"
            await self._upsert_node(merchant_node, "merchant", str(merchant_id), now)
            if device_id:
                await self._upsert_edge(f"device:{device_id}", merchant_node, "device_merchant", now)

        await self.db.flush()

    async def compute_graph_risk(
        self,
        auth_event_id: int,
        account_id: int,
        device_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        max_hops: int = 2,
    ) -> FactGraphClusterScore:
        """
        Compute fraud risk based on graph neighborhood.
        Equivalent to DRA's blast-radius traversal but for fraud cluster expansion.
        """
        G = self._graph or await self.build_graph_from_db()
        account_node = f"account:{account_id}"

        if account_node not in G:
            return await self._store_empty_cluster_score(auth_event_id)

        neighbors = self._get_hop_neighbors(G, account_node, max_hops)
        cluster_nodes = {account_node} | neighbors

        risky_count = sum(
            1 for n in cluster_nodes
            if G.nodes[n].get("risk_score", 0) > 0.5
        )

        hop2_scores = [
            G.nodes[n].get("risk_score", 0) for n in neighbors
        ]
        hop2_risk = sum(hop2_scores) / len(hop2_scores) if hop2_scores else 0.0

        synthetic_flag = self._detect_synthetic_identity(G, cluster_nodes)
        mule_flag = self._detect_mule_pattern(G, cluster_nodes)

        cluster_id = self._find_cluster_id(G, account_node)

        score = FactGraphClusterScore(
            auth_event_id=auth_event_id,
            cluster_id=cluster_id,
            cluster_size=len(cluster_nodes),
            risky_neighbor_count=risky_count,
            hop2_risk_score=hop2_risk,
            synthetic_identity_flag=synthetic_flag,
            mule_pattern_flag=mule_flag,
            score_time=datetime.now(timezone.utc),
        )
        self.db.add(score)
        await self.db.flush()

        logger.info(
            "graph_risk_computed",
            auth_event_id=auth_event_id,
            cluster_size=len(cluster_nodes),
            hop2_risk=hop2_risk,
            synthetic=synthetic_flag,
            mule=mule_flag,
        )
        return score

    async def find_fraud_rings(self, min_size: int = 3) -> list[dict]:
        """Identify connected components that look like fraud rings."""
        G = self._graph or await self.build_graph_from_db()
        rings = []

        for component in nx.connected_components(G):
            if len(component) < min_size:
                continue

            subgraph = G.subgraph(component)
            account_nodes = [n for n in component if G.nodes[n].get("node_type") == "account"]
            if len(account_nodes) < 2:
                continue

            avg_risk = sum(
                G.nodes[n].get("risk_score", 0) for n in component
            ) / len(component)

            shared_devices = sum(
                1 for n in component if G.nodes[n].get("node_type") == "device"
            )
            shared_ips = sum(
                1 for n in component if G.nodes[n].get("node_type") == "ip"
            )

            ring_score = 0.0
            if len(account_nodes) >= 3 and shared_devices >= 1:
                ring_score += 0.3
            if shared_ips >= 1 and len(account_nodes) >= 2:
                ring_score += 0.2
            ring_score += avg_risk * 0.5

            if ring_score > 0.3:
                rings.append({
                    "cluster_id": min(component),
                    "node_count": len(component),
                    "account_count": len(account_nodes),
                    "shared_devices": shared_devices,
                    "shared_ips": shared_ips,
                    "avg_risk_score": avg_risk,
                    "ring_score": min(ring_score, 1.0),
                    "nodes": list(component)[:50],
                })

        rings.sort(key=lambda r: r["ring_score"], reverse=True)
        logger.info("fraud_rings_detected", ring_count=len(rings))
        return rings

    async def expand_cluster(self, node_id: str, max_hops: int = 3) -> dict:
        """Expand from a given node to find the full cluster — for investigator use."""
        G = self._graph or await self.build_graph_from_db()
        if node_id not in G:
            return {"error": f"Node {node_id} not found"}

        neighbors_by_hop = {}
        for hop in range(1, max_hops + 1):
            hop_nodes = self._get_hop_neighbors(G, node_id, hop)
            neighbors_by_hop[f"hop_{hop}"] = [
                {
                    "node_id": n,
                    "node_type": G.nodes[n].get("node_type"),
                    "risk_score": G.nodes[n].get("risk_score", 0),
                }
                for n in hop_nodes
            ]

        return {
            "center_node": node_id,
            "neighbors_by_hop": neighbors_by_hop,
            "total_reachable": sum(len(v) for v in neighbors_by_hop.values()),
        }

    async def update_node_risk(self, node_id: str, risk_score: float):
        result = await self.db.execute(
            select(GraphEntityNode).where(GraphEntityNode.node_id == node_id)
        )
        node = result.scalar_one_or_none()
        if node:
            node.risk_score = risk_score
            node.last_seen_at = datetime.now(timezone.utc)
            if self._graph and node_id in self._graph:
                self._graph.nodes[node_id]["risk_score"] = risk_score

    def _get_hop_neighbors(self, G: nx.Graph, node: str, max_hops: int) -> set:
        visited = set()
        frontier = {node}
        for _ in range(max_hops):
            next_frontier = set()
            for n in frontier:
                for neighbor in G.neighbors(n):
                    if neighbor not in visited and neighbor != node:
                        next_frontier.add(neighbor)
            visited.update(next_frontier)
            frontier = next_frontier
        return visited

    def _detect_synthetic_identity(self, G: nx.Graph, cluster_nodes: set) -> bool:
        """
        Synthetic identity pattern: multiple accounts sharing unusual combinations
        of devices and addresses, but with no shared email or phone.
        """
        accounts = [n for n in cluster_nodes if G.nodes[n].get("node_type") == "account"]
        devices = [n for n in cluster_nodes if G.nodes[n].get("node_type") == "device"]
        emails = [n for n in cluster_nodes if G.nodes[n].get("node_type") == "email"]

        if len(accounts) >= 3 and len(devices) >= 2 and len(emails) <= 1:
            return True
        return False

    def _detect_mule_pattern(self, G: nx.Graph, cluster_nodes: set) -> bool:
        """
        Mule pattern: account receives funds and immediately redistributes
        across multiple other accounts via shared devices/IPs.
        """
        accounts = [n for n in cluster_nodes if G.nodes[n].get("node_type") == "account"]
        if len(accounts) < 4:
            return False

        for account in accounts:
            neighbors = set(G.neighbors(account))
            shared_with_accounts = sum(
                1 for n in neighbors
                if G.nodes[n].get("node_type") in ("device", "ip")
                and sum(1 for nn in G.neighbors(n) if G.nodes[nn].get("node_type") == "account") >= 3
            )
            if shared_with_accounts >= 2:
                return True
        return False

    def _find_cluster_id(self, G: nx.Graph, node: str) -> str:
        for component in nx.connected_components(G):
            if node in component:
                return min(component)
        return node

    async def _store_empty_cluster_score(self, auth_event_id: int) -> FactGraphClusterScore:
        score = FactGraphClusterScore(
            auth_event_id=auth_event_id,
            cluster_id=None,
            cluster_size=0,
            risky_neighbor_count=0,
            hop2_risk_score=0.0,
            synthetic_identity_flag=False,
            mule_pattern_flag=False,
            score_time=datetime.now(timezone.utc),
        )
        self.db.add(score)
        await self.db.flush()
        return score

    async def _upsert_node(
        self, node_id: str, node_type: str, entity_ref: str, now: datetime
    ):
        result = await self.db.execute(
            select(GraphEntityNode).where(GraphEntityNode.node_id == node_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.last_seen_at = now
            return

        node = GraphEntityNode(
            node_id=node_id,
            node_type=node_type,
            entity_ref=entity_ref,
            first_seen_at=now,
            last_seen_at=now,
        )
        self.db.add(node)

    async def _upsert_edge(
        self, src: str, dst: str, edge_type: str, now: datetime
    ):
        result = await self.db.execute(
            select(GraphEntityEdge).where(
                and_(
                    GraphEntityEdge.src_node_id == src,
                    GraphEntityEdge.dst_node_id == dst,
                    GraphEntityEdge.edge_type == edge_type,
                )
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.last_seen_at = now
            existing.weight = float(existing.weight or 1) + 1
            return

        edge = GraphEntityEdge(
            src_node_id=src,
            dst_node_id=dst,
            edge_type=edge_type,
            weight=1.0,
            first_seen_at=now,
            last_seen_at=now,
        )
        self.db.add(edge)
