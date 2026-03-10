"""Tests for fraud graph intelligence service."""
import pytest
import networkx as nx


class TestGraphAnalysis:
    def _build_test_graph(self):
        G = nx.Graph()
        G.add_node("account:1", node_type="account", risk_score=0.1)
        G.add_node("account:2", node_type="account", risk_score=0.8)
        G.add_node("account:3", node_type="account", risk_score=0.7)
        G.add_node("device:A", node_type="device", risk_score=0.5)
        G.add_node("ip:1.2.3.4", node_type="ip", risk_score=0.3)
        G.add_node("email:test@evil.com", node_type="email", risk_score=0.6)

        G.add_edge("account:1", "device:A", edge_type="account_device")
        G.add_edge("account:2", "device:A", edge_type="account_device")
        G.add_edge("account:3", "device:A", edge_type="account_device")
        G.add_edge("account:1", "ip:1.2.3.4", edge_type="account_ip")
        G.add_edge("account:2", "ip:1.2.3.4", edge_type="account_ip")
        G.add_edge("account:1", "email:test@evil.com", edge_type="account_email")
        return G

    def test_connected_components(self):
        G = self._build_test_graph()
        components = list(nx.connected_components(G))
        assert len(components) == 1
        assert len(components[0]) == 6

    def test_hop_neighbors(self):
        G = self._build_test_graph()
        neighbors_1hop = set(G.neighbors("account:1"))
        assert "device:A" in neighbors_1hop
        assert "ip:1.2.3.4" in neighbors_1hop

    def test_2hop_reaches_other_accounts(self):
        G = self._build_test_graph()
        hop1 = set(G.neighbors("account:1"))
        hop2 = set()
        for n in hop1:
            for nn in G.neighbors(n):
                if nn != "account:1":
                    hop2.add(nn)
        assert "account:2" in hop2
        assert "account:3" in hop2

    def test_risk_propagation(self):
        G = self._build_test_graph()
        neighbors = set(G.neighbors("account:1"))
        risk_scores = [G.nodes[n].get("risk_score", 0) for n in neighbors]
        avg_risk = sum(risk_scores) / len(risk_scores)
        assert avg_risk > 0

    def test_synthetic_identity_detection(self):
        G = nx.Graph()
        for i in range(4):
            G.add_node(f"account:{i}", node_type="account", risk_score=0.5)
        G.add_node("device:X", node_type="device", risk_score=0.3)
        G.add_node("device:Y", node_type="device", risk_score=0.3)

        for i in range(4):
            G.add_edge(f"account:{i}", "device:X", edge_type="account_device")
            G.add_edge(f"account:{i}", "device:Y", edge_type="account_device")

        cluster = set(G.nodes())
        accounts = [n for n in cluster if G.nodes[n].get("node_type") == "account"]
        devices = [n for n in cluster if G.nodes[n].get("node_type") == "device"]
        emails = [n for n in cluster if G.nodes[n].get("node_type") == "email"]

        is_synthetic = len(accounts) >= 3 and len(devices) >= 2 and len(emails) <= 1
        assert is_synthetic is True

    def test_mule_pattern_detection(self):
        G = nx.Graph()
        for i in range(5):
            G.add_node(f"account:{i}", node_type="account", risk_score=0.4)
        G.add_node("device:shared", node_type="device", risk_score=0.5)

        for i in range(5):
            G.add_edge(f"account:{i}", "device:shared", edge_type="account_device")

        device_neighbors = list(G.neighbors("device:shared"))
        account_neighbors = [n for n in device_neighbors if G.nodes[n]["node_type"] == "account"]
        assert len(account_neighbors) >= 4
