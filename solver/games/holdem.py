"""Heads-up No-Limit Hold'em postflop game for Deep CFR.

Supports full postflop play across flop, turn, and river streets.
Uses the existing HUState from engine.state for state representation.

This game implementation is designed for Deep CFR with neural network
value estimation, allowing the solver to generalize across similar
board textures and hand strengths.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from typing import Optional

from engine.actions import Action, ActionKind
from engine.cards import Card, Deck, mask_to_cards
from engine.evaluator import evaluate7
from engine.state import HUState, apply_action, initial_state, legal_actions


@dataclass(frozen=True)
class PostflopState:
    """Extended state for full postflop play.
    
    Wraps HUState and adds game-level information like
    the full board and betting configuration.
    """
    
    hu_state: HUState
    full_board: tuple[Card, ...]  # Complete 5-card board
    street: int                   # 0=flop, 1=turn, 2=river
    
    @property
    def is_terminal(self) -> bool:
        return self.hu_state.is_terminal()
    
    @property
    def current_player(self) -> int:
        return self.hu_state.to_act


@dataclass(frozen=True)
class BettingConfig:
    """Betting configuration for postflop play."""
    
    stack: int = 100
    pot: int = 10
    bet_sizings: tuple[float, ...] = (0.5, 0.75, 1.0)
    max_raises: int = 4
    
    @property
    def all_in_threshold(self) -> int:
        return self.stack


class PostflopGame:
    """Heads-up No-Limit Hold'em postflop game.
    
    Implements the Game protocol for Deep CFR.
    Handles flop/turn/river play with configurable bet sizings.
    
    Key features:
    - Multi-street play (flop -> turn -> river)
    - Configurable bet sizings
    - Proper showdown evaluation
    - Support for card abstraction (future)
    """
    
    num_players = 2
    
    def __init__(self, config: Optional[BettingConfig] = None):
        self.config = config or BettingConfig()
        self._rng = random.Random(42)
    
    def _random_board(self) -> tuple[Card, ...]:
        """Generate a random 5-card board."""
        deck = Deck()
        deck.shuffle(self._rng)
        return tuple(deck.deal(5))
    
    def _random_hole(self) -> tuple[tuple[Card, Card], tuple[Card, Card]]:
        """Generate random hole cards for both players (no board conflicts)."""
        deck = Deck()
        deck.shuffle(self._rng)
        cards = deck.deal(4)
        return ((cards[0], cards[1]), (cards[2], cards[3]))
    
    def initial_state(self) -> PostflopState:
        """Create initial postflop state with random cards."""
        board = self._random_board()
        hole = self._random_hole()
        
        hu = initial_state(
            stacks=(self.config.stack, self.config.stack),
            pot=self.config.pot,
            hole=hole,
            board=board[:3],  # Start with flop
        )
        
        return PostflopState(
            hu_state=hu,
            full_board=board,
            street=0,
        )
    
    def is_terminal(self, state: PostflopState) -> bool:
        """Check if state is terminal (fold or showdown)."""
        return state.is_terminal
    
    def is_chance(self, state: PostflopState) -> bool:
        """Check if state is a chance node (dealing cards).
        
        In postflop, chance only occurs at the start when dealing
        hole cards and board. For Deep CFR training, we pre-deal
        all cards and treat the game as having no chance nodes.
        """
        return False
    
    def chance_outcomes(self, state: PostflopState):
        """Not used in pre-dealt postflop."""
        return []
    
    def apply_chance(self, state: PostflopState, outcome):
        """Not used in pre-dealt postflop."""
        return state
    
    def current_player(self, state: PostflopState) -> int:
        """Get current player (0=OOP, 1=IP)."""
        return state.current_player
    
    def legal_actions(self, state: PostflopState) -> list[Action]:
        """Get legal actions for current state."""
        return legal_actions(state.hu_state, self.config.bet_sizings)
    
    def apply(self, state: PostflopState, action: Action) -> PostflopState:
        """Apply action and advance street if needed."""
        new_hu = apply_action(state.hu_state, action)
        
        # Check if street advanced
        if len(new_hu.board) > len(state.hu_state.board):
            # Street advanced - update full board reference
            new_street = state.street + 1
            return PostflopState(
                hu_state=new_hu,
                full_board=state.full_board,
                street=new_street,
            )
        
        return PostflopState(
            hu_state=new_hu,
            full_board=state.full_board,
            street=state.street,
        )
    
    def utility(self, state: PostflopState, player: int) -> float:
        """Compute utility for player at terminal state.
        
        Positive = player wins chips, negative = player loses chips.
        """
        hu = state.hu_state
        
        if hu.folded is not None:
            # Someone folded - other player wins pot
            folded = hu.folded
            if folded == player:
                # Player folded - lose committed chips
                return -float(hu.committed[player])
            else:
                # Opponent folded - win pot + opponent's committed
                return float(hu.pot + hu.committed[1 - player])
        
        # Showdown
        total_pot = hu.pot + hu.committed[0] + hu.committed[1]
        
        # Evaluate hands
        hole = hu.hole[player]
        board = hu.board
        
        # Create 7-card bitmask
        mask = hole[0].mask | hole[1].mask
        for card in board:
            mask |= card.mask
        
        opp_hole = hu.hole[1 - player]
        opp_mask = opp_hole[0].mask | opp_hole[1].mask
        for card in board:
            opp_mask |= card.mask
        
        try:
            player_hand = evaluate7(mask)
            opp_hand = evaluate7(opp_mask)
        except ValueError:
            # Invalid hand (shouldn't happen with valid cards)
            return 0.0
        
        if player_hand > opp_hand:
            # Player wins
            return float(total_pot - hu.committed[player])
        elif player_hand < opp_hand:
            # Player loses
            return -float(hu.committed[player])
        else:
            # Split pot
            return float(total_pot / 2 - hu.committed[player])
    
    def infoset_key(self, state: PostflopState, player: int) -> str:
        """Generate infoset key for neural network input.
        
        Format: "street|player|board|history"
        """
        hu = state.hu_state
        
        # Street
        key = f"{state.street}|{player}|"
        
        # Board cards
        board_str = ",".join(str(c) for c in hu.board)
        key += f"{board_str}|"
        
        # Hole cards (for abstraction, could use hand class)
        hole = hu.hole[player]
        key += f"{hole[0]}{hole[1]}|"
        
        # Action history
        history_str = ",".join(
            f"{a.kind.name}:{a.amount}" if a.amount else a.kind.name
            for a in hu.history
        )
        key += history_str
        
        return key
    
    def clone_state(self, state: PostflopState) -> PostflopState:
        """Create a deep copy of the state."""
        return PostflopState(
            hu_state=replace(state.hu_state),
            full_board=state.full_board,
            street=state.street,
        )


class PostflopGameWithBoard(PostflopGame):
    """Postflop game with fixed board for analysis.
    
    Useful for studying specific board textures.
    """
    
    def __init__(self, board: tuple[Card, ...], config: Optional[BettingConfig] = None):
        super().__init__(config)
        self.fixed_board = board
    
    def initial_state(self) -> PostflopState:
        """Create initial state with fixed board."""
        hole = self._random_hole()
        
        hu = initial_state(
            stacks=(self.config.stack, self.config.stack),
            pot=self.config.pot,
            hole=hole,
            board=self.fixed_board[:3],
        )
        
        return PostflopState(
            hu_state=hu,
            full_board=self.fixed_board,
            street=0,
        )


def create_postflop_game(
    stack: int = 100,
    pot: int = 10,
    bet_sizings: tuple[float, ...] = (0.5, 0.75, 1.0),
) -> PostflopGame:
    """Factory function to create a postflop game."""
    config = BettingConfig(
        stack=stack,
        pot=pot,
        bet_sizings=bet_sizings,
    )
    return PostflopGame(config)
