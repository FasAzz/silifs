import random
from dataclasses import dataclass


@dataclass
class NodeInfo:
    node_id: str
    address: str
    capacity_bytes: int
    free_bytes: int
    chunk_count: int = 0
    last_heartbeat: float = 0.0
    alive: bool = True


class RandomPlacement:
    """Pilih rf node secara acak."""
    name = "random"

    def choose(self, nodes, rf, chunk_size):
        return random.sample(nodes, rf)


class RoundRobinPlacement:
    """Pilih rf node berurutan, titik awalnya bergeser 1 tiap chunk."""
    name = "round_robin"

    def __init__(self):
        self.pointer = 0

    def choose(self, nodes, rf, chunk_size):
        n = len(nodes)
        picked = [nodes[(self.pointer + i) % n] for i in range(rf)]
        self.pointer = (self.pointer + 1) % n
        return picked


class CapacityAwarePlacement:
    """Pilih rf node dengan sisa disk terbanyak."""
    name = "capacity_aware"

    def choose(self, nodes, rf, chunk_size):
        ranked = sorted(nodes, key=lambda x: x.free_bytes, reverse=True)
        picked = ranked[:rf]
        # Tandai ruang terpakai sementara, supaya chunk berikutnya
        # tidak menumpuk di node yang sama sebelum heartbeat berikutnya.
        for node in picked:
            node.free_bytes -= chunk_size
        return picked


STRATEGIES = {
    "random": RandomPlacement,
    "round_robin": RoundRobinPlacement,
    "capacity_aware": CapacityAwarePlacement,
}


def get_strategy(name):
    return STRATEGIES[name]()