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
        self.peers = peers  # Liste von Referenzen auf andere Nodes
        self.messages: Dict[str, Message] = {}
        self.known_message_ids = set()
        self.reputation_scores: Dict[str, float] = {}
        # Initialisiere alle Peers mit mittlerer Reputation
        for p in peers:
            if p.node_id != self.node_id:
                self.reputation_scores[p.node_id] = 0.5
        
        # Interne Parameter
        self.decay_factor = 0.99    # Reputation sinkt langsam über die Zeit
        self.push_pull_interval = 2 # Sekunden zwischen Gossip-Runden

    def add_message(self, msg: Message):
        if msg.msg_id not in self.known_message_ids:
            self.known_message_ids.add(msg.msg_id)
            self.messages[msg.msg_id] = msg

    def get_missing_message_ids(self, known_ids: set):
        # Welche Nachrichten habe ich, die der andere nicht hat?
        return set(self.known_message_ids) - known_ids

    def receive_gossip(self, from_node_id: str, messages: List[Message], reputations: Dict[str, float]):
        # Empfange Nachrichten
        for m in messages:
            self.add_message(m)
        
        # Update Reputation gemäß erhaltenen Werten
        # Hier einfache Logik: Mittelwert bilden
        for node_id, rep_val in reputations.items():
            if node_id not in self.reputation_scores:
                self.reputation_scores[node_id] = rep_val
            else:
                # Aggregation: Mittelwertbildung (oder Bayesianische Schätzung)
                self.reputation_scores[node_id] = (self.reputation_scores[node_id] + rep_val) / 2
        
        # Feedback-Mechanismus: Gebe einfach positives Feedback, wenn Nachrichten empfangen wurden
        # In einem echten Szenario könnte hier Logik sein, ob Nachrichten veraltet/Spam sind.
        self.update_reputation(from_node_id, positive=True)

    def update_reputation(self, node_id: str, positive: bool = True):
        # Einfache Heuristik: bei positivem Feedback steigt Reputation leicht, bei negativem sinkt sie.
        if node_id not in self.reputation_scores:
            self.reputation_scores[node_id] = 0.5
        change = 0.05 if positive else -0.05
        self.reputation_scores[node_id] = max(0.0, min(1.0, self.reputation_scores[node_id] + change))

    def apply_decay(self):
        # Reputation langsam absenken, so dass ältere Daten weniger relevant werden
        for node_id in self.reputation_scores:
            self.reputation_scores[node_id] *= self.decay_factor

    async def gossip_cycle(self):
        # Wähle einen zufälligen Peer (mit Gewichtung nach Reputation?)
        # Hier einfach zufällig:
        candidates = [p for p in self.peers if p.node_id != self.node_id]
        if not candidates:
            return
        partner = random.choice(candidates)

        # Push: Sende dem Partner meine Nachrichten & Reputationen
        await partner.async_receive_gossip(
            from_node_id=self.node_id,
            messages=list(self.messages.values()),
            reputations=self.reputation_scores
        )

        # Pull: Frage nach fehlenden Nachrichten des Partners
        missing_ids = partner.get_missing_message_ids(self.known_message_ids)
        # Holen wir diese über einen (in echt asynchronen) Aufruf
        if missing_ids:
            new_msgs = [partner.messages[mid] for mid in missing_ids if mid in partner.messages]
            for m in new_msgs:
                self.add_message(m)

        # Decay anwenden
        self.apply_decay()

    async def async_receive_gossip(self, from_node_id: str, messages: List[Message], reputations: Dict[str, float]):
        # Asynchroner Wrapper für receive_gossip
        self.receive_gossip(from_node_id, messages, reputations)
    
    async def run(self):
        # Kontinuierliche Gossip-Zyklen
        while True:
            await self.gossip_cycle()
            await asyncio.sleep(self.push_pull_interval)

async def main():
    # Erzeuge ein kleines P2P-Netz mit 4 Knoten
    nodes = []
    for i in range(4):
        n = Node(node_id=f"Node_{i}", peers=[])
        nodes.append(n)
    # Peers verlinken
    for n in nodes:
        n.peers = [p for p in nodes if p.node_id != n.node_id]

    # Erstelle initiale Nachrichten
    nodes[0].add_message(Message("msg_1", "Hallo von Node_0"))
    nodes[1].add_message(Message("msg_2", "Grüße von Node_1"))

    # Starte die Gossip-Loops
    tasks = [asyncio.create_task(n.run()) for n in nodes]

    # Lass das Ganze einige Sekunden laufen und beobachte die Ausbreitung
    await asyncio.sleep(10)

    # Stoppe die Tasks (in dieser vereinfachten Demo durch Cancel)
    for t in tasks:
        t.cancel()
    
    # Ergebnisse anzeigen
    for n in nodes:
        print(f"--- {n.node_id} ---")
        print("Bekannte Nachrichten:")
        for msg_id, msg in n.messages.items():
            print(f"{msg_id}: {msg.content}")
        print("Reputationen:")
        for nid, rep in n.reputation_scores.items():
            print(f"{nid}: {rep:.2f}")
        print("--------------")

# Ausführen
if __name__ == "__main__":
    asyncio.run(main())
