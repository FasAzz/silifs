from collections import Counter
from master.placement import NodeInfo, get_strategy

GB = 1024 ** 3
MB = 1024 ** 2

for name in ["random", "round_robin", "capacity_aware"]:
    nodes = [NodeInfo(f"node{i}", f"datanode{i}:50052", 10 * GB, 10 * GB)
             for i in range(1, 6)]
    # sengaja dibuat tidak seimbang: node1 hampir penuh
    nodes[0].free_bytes = 1 * GB

    strategy = get_strategy(name)
    count = Counter()
    for _ in range(1000):
        for node in strategy.choose(nodes, rf=2, chunk_size=4 * MB):
            count[node.node_id] += 1

    print(name, dict(sorted(count.items())))