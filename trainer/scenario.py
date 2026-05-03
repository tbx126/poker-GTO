"""Training scenario generation.

Generates training scenarios for specific poker situations:
- Preflop decisions
- Postflop play
- Specific board textures
- Position-based training
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from engine.cards import Card, Deck, card_from_str
from engine.state import HUState, initial_state
from solver.preflop import PreflopSolver, TreeCfg


class SituationType(Enum):
    """Types of training situations."""
    PREFLOP_OPEN = "preflop_open"
    PREFLOP_3BET = "preflop_3bet"
    PREFLOP_4BET = "preflop_4bet"
    FLOP_CBET = "flop_cbet"
    FLOP_RAISE = "flop_raise"
    TURN_BARREL = "turn_barrel"
    RIVER_CALL = "river_call"
    RIVER_BLUFF = "river_bluff"


@dataclass
class Scenario:
    """A training scenario."""
    scenario_id: str
    situation_type: SituationType
    description: str
    
    # Game state
    stacks: tuple[int, int]  # (player, opponent)
    pot: int
    board: list[Card] = field(default_factory=list)
    hole: tuple[Card, Card] = (Card(0), Card(1))
    
    # Actions available
    actions: list[str] = field(default_factory=list)
    
    # GTO solution for reference
    gto_strategy: dict[str, float] = field(default_factory=dict)
    
    # Metadata
    difficulty: int = 1  # 1-5
    tags: list[str] = field(default_factory=list)


class ScenarioGenerator:
    """Generates training scenarios."""
    
    def __init__(self, preflop_solver: Optional[PreflopSolver] = None):
        self.preflop_solver = preflop_solver
        self.rng = random.Random(42)
    
    def generate_preflop_open(self, position: str = "BTN", stack_depth: int = 100) -> Scenario:
        """Generate a preflop opening scenario."""
        # Create random hand
        deck = Deck()
        deck.shuffle(self.rng)
        hole = (deck.deal(1)[0], deck.deal(1)[0])
        
        # Determine actions based on position
        if position == "BTN":
            actions = ["fold", "open", "shove"]
            description = f"BTN open with {hole[0]}{hole[1]}, {stack_depth}bb"
        elif position == "BB":
            actions = ["fold", "call", "3bet"]
            description = f"BB defend with {hole[0]}{hole[1]}, {stack_depth}bb"
        else:
            actions = ["fold", "open", "shove"]
            description = f"{position} open with {hole[0]}{hole[1]}, {stack_depth}bb"
        
        # Get GTO strategy if solver available
        gto_strategy = {}
        if self.preflop_solver:
            from engine.hand_class import combo_to_class_label
            hand_class = combo_to_class_label(hole[0], hole[1])
            # Would need to look up from solver
        
        return Scenario(
            scenario_id=f"preflop_{position}_{self.rng.randint(1000, 9999)}",
            situation_type=SituationType.PREFLOP_OPEN,
            description=description,
            stacks=(stack_depth, stack_depth),
            pot=1,  # Blinds
            hole=hole,
            actions=actions,
            gto_strategy=gto_strategy,
            difficulty=1,
            tags=["preflop", position.lower(), f"{stack_depth}bb"],
        )
    
    def generate_preflop_3bet(self, opener_position: str = "BTN", stack_depth: int = 100) -> Scenario:
        """Generate a preflop 3-bet scenario."""
        deck = Deck()
        deck.shuffle(self.rng)
        hole = (deck.deal(1)[0], deck.deal(1)[0])
        
        open_size = 2.5
        actions = ["fold", "call", "3bet"]
        description = f"BB 3-bet vs {opener_position} open with {hole[0]}{hole[1]}"
        
        return Scenario(
            scenario_id=f"preflop_3bet_{self.rng.randint(1000, 9999)}",
            situation_type=SituationType.PREFLOP_3BET,
            description=description,
            stacks=(stack_depth, stack_depth),
            pot=int(open_size * 2),
            hole=hole,
            actions=actions,
            gto_strategy={},
            difficulty=2,
            tags=["preflop", "3bet", f"{stack_depth}bb"],
        )
    
    def generate_flop_cbet(self, board_texture: str = "dry") -> Scenario:
        """Generate a flop continuation bet scenario."""
        deck = Deck()
        deck.shuffle(self.rng)
        
        # Generate board based on texture
        if board_texture == "dry":
            # Low, disconnected board
            board = [Card(i) for i in [0, 5, 10]]  # 2c, 6h, Jd
        elif board_texture == "wet":
            # Connected, suited board
            board = [Card(i) for i in [1, 2, 3]]  # 2d, 3c, 4h
        else:
            board = deck.deal(3)
        
        hole = (deck.deal(1)[0], deck.deal(1)[0])
        pot = 10
        stack = 100
        
        actions = ["check", "bet_small", "bet_medium", "bet_large"]
        description = f"Flop cbet on {board[0]}{board[1]}{board[2]} with {hole[0]}{hole[1]}"
        
        return Scenario(
            scenario_id=f"flop_cbet_{self.rng.randint(1000, 9999)}",
            situation_type=SituationType.FLOP_CBET,
            description=description,
            stacks=(stack, stack),
            pot=pot,
            board=board,
            hole=hole,
            actions=actions,
            gto_strategy={},
            difficulty=2,
            tags=["flop", "cbet", board_texture],
        )
    
    def generate_river_call(self, bet_size: str = "pot") -> Scenario:
        """Generate a river calling decision scenario."""
        deck = Deck()
        deck.shuffle(self.rng)
        
        board = deck.deal(5)
        hole = (deck.deal(1)[0], deck.deal(1)[0])
        pot = 20
        
        if bet_size == "small":
            bet = int(pot * 0.5)
        elif bet_size == "pot":
            bet = pot
        else:
            bet = int(pot * 1.5)
        
        actions = ["fold", "call", "raise"]
        description = f"River call {bet_size} bet with {hole[0]}{hole[1]}"
        
        return Scenario(
            scenario_id=f"river_call_{self.rng.randint(1000, 9999)}",
            situation_type=SituationType.RIVER_CALL,
            description=description,
            stacks=(100, 100),
            pot=pot + bet,
            board=list(board),
            hole=hole,
            actions=actions,
            gto_strategy={},
            difficulty=3,
            tags=["river", "call", bet_size],
        )
    
    def generate_random_scenario(self, difficulty: int = 1) -> Scenario:
        """Generate a random scenario based on difficulty."""
        scenarios = {
            1: [
                lambda: self.generate_preflop_open("BTN"),
                lambda: self.generate_preflop_open("CO"),
            ],
            2: [
                lambda: self.generate_preflop_3bet(),
                lambda: self.generate_flop_cbet("dry"),
            ],
            3: [
                lambda: self.generate_flop_cbet("wet"),
                lambda: self.generate_river_call("pot"),
            ],
        }
        
        scenario_list = scenarios.get(difficulty, scenarios[1])
        return self.rng.choice(scenario_list)()
    
    def generate_training_set(self, num_scenarios: int = 10, difficulty: int = 1) -> list[Scenario]:
        """Generate a set of training scenarios."""
        return [self.generate_random_scenario(difficulty) for _ in range(num_scenarios)]
