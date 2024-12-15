import asyncio
import random
import time
from typing import Dict, List


class Message:
    def __init__(self, msg_id: str, content: str, timestamp: float = None):
        self.msg_id = msg_id
        self.content = content
        self.timestamp = timestamp if timestamp else time.time()


class Node:
    def __init__(self, node_id: str, peers: List['Node']):
        self.node_id = node_id
        self.peers = peers  # List of references to other nodes
        self.messages: Dict[str, Message] = {}
        self.known_message_ids = set()
        self.reputation_scores: Dict[str, float] = {}
        # Initialize all peers with medium reputation
        for p in peers:
            if p.node_id != self.node_id:
                self.reputation_scores[p.node_id] = 0.5

        # Internal parameters
        self.decay_factor = 0.99    # Reputation decreases slowly over time
        self.push_pull_interval = 2  # Seconds between gossip rounds

    def add_message(self, msg: Message):
        if msg.msg_id not in self.known_message_ids:
            self.known_message_ids.add(msg.msg_id)
            self.messages[msg.msg_id] = msg

    def get_missing_message_ids(self, known_ids: set):
        # Which messages do I have that the other does not?
        return set(self.known_message_ids) - known_ids

    def receive_gossip(self, from_node_id: str, messages: List[Message], reputations: Dict[str, float]):
        # Receive messages
        for m in messages:
            self.add_message(m)

        # Update reputation based on received values
        # Simple logic here: calculate the average
        for node_id, rep_val in reputations.items():
            if node_id not in self.reputation_scores:
                self.reputation_scores[node_id] = rep_val
            else:
                # Aggregation: calculate the average (or Bayesian estimation)
                self.reputation_scores[node_id] = (
                    self.reputation_scores[node_id] + rep_val) / 2

        # Feedback mechanism: Simply give positive feedback if messages were received
        # In a real scenario, logic could be added to determine whether messages are outdated or spam.
        self.update_reputation(from_node_id, positive=True)

    def update_reputation(self, node_id: str, positive: bool = True):
        # Simple heuristic: reputation increases slightly with positive feedback, decreases with negative feedback
        if node_id not in self.reputation_scores:
            self.reputation_scores[node_id] = 0.5
        change = 0.05 if positive else -0.05
        self.reputation_scores[node_id] = max(
            0.0, min(1.0, self.reputation_scores[node_id] + change))

    def apply_decay(self):
        # Slowly decrease reputation so that older data becomes less relevant
        for node_id in self.reputation_scores:
            self.reputation_scores[node_id] *= self.decay_factor

    async def gossip_cycle(self):
        # Choose a random peer (weighted by reputation?)
        # Here simply random:
        candidates = [p for p in self.peers if p.node_id != self.node_id]
        if not candidates:
            return
        partner = random.choice(candidates)

        # Push: Send my messages & reputations to the partner
        await partner.async_receive_gossip(
            from_node_id=self.node_id,
            messages=list(self.messages.values()),
            reputations=self.reputation_scores
        )

        # Pull: Request missing messages from the partner
        missing_ids = partner.get_missing_message_ids(self.known_message_ids)
        # Retrieve these through a (real asynchronous) call
        if missing_ids:
            new_msgs = [partner.messages[mid]
                        for mid in missing_ids if mid in partner.messages]
            for m in new_msgs:
                self.add_message(m)

        # Apply decay
        self.apply_decay()

    async def async_receive_gossip(self, from_node_id: str, messages: List[Message], reputations: Dict[str, float]):
        # Asynchronous wrapper for receive_gossip
        self.receive_gossip(from_node_id, messages, reputations)

    async def run(self):
        # Continuous gossip cycles
        while True:
            await self.gossip_cycle()
            await asyncio.sleep(self.push_pull_interval)


async def main():
    # Create a small P2P network with 4 nodes
    nodes = []
    for i in range(4):
        n = Node(node_id=f"Node_{i}", peers=[])
        nodes.append(n)
    # Link peers
    for n in nodes:
        n.peers = [p for p in nodes if p.node_id != n.node_id]

    # Create initial messages
    nodes[0].add_message(Message("msg_1", "Hello from Node_0"))
    nodes[1].add_message(Message("msg_2", "Greetings from Node_1"))

    # Start the gossip loops
    tasks = [asyncio.create_task(n.run()) for n in nodes]

    # Let it run for a few seconds and observe the propagation
    await asyncio.sleep(10)

    # Stop the tasks (in this simplified demo by canceling)
    for t in tasks:
        t.cancel()

    # Display results
    for n in nodes:
        print(f"--- {n.node_id} ---")
        print("Known messages:")
        for msg_id, msg in n.messages.items():
            print(f"{msg_id}: {msg.content}")
        print("Reputations:")
        for nid, rep in n.reputation_scores.items():
            print(f"{nid}: {rep:.2f}")
        print("--------------")

# Execute
if __name__ == "__main__":
    asyncio.run(main())
