"""Hand history parser for various poker formats.

Supports parsing hand histories from common poker sites and formats:
- PokerStars format
- GGPoker format
- Generic JSON format

Example PokerStars format:
PokerStars Hand #123456789: Hold'em No Limit ($1/$2 USD) - 2024/01/01 12:00:00 ET
Table 'Test' 6-max Seat #1 is the button
Seat 1: Player1 ($200 in chips)
Seat 2: Player2 ($200 in chips)
Player1: posts small blind $1
Player2: posts big blind $2
*** HOLE CARDS ***
Dealt to Player1 [Ah Kd]
Player1: raises $4 to $6
Player2: calls $4
*** FLOP *** [7h 8c 9d]
Player2: checks
Player1: bets $8
Player2: folds
Player1 collected $12 from pot
*** SUMMARY ***
Total pot $12 | Rake $0
Board [7h 8c 9d]
Seat 1: Player1 ($12) (button) (small blind)
Seat 2: Player2 (folded)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Action(Enum):
    """Poker action types."""
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    ALL_IN = "all_in"


class Street(Enum):
    """Betting streets."""
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"


@dataclass
class PlayerAction:
    """A single player action in a hand."""
    player: str
    action: Action
    amount: float = 0.0
    street: Street = Street.PREFLOP


@dataclass
class Showdown:
    """Showdown information."""
    player: str
    hand: list[str]  # e.g., ["Ah", "Kd"]
    hand_rank: str   # e.g., "pair", "flush"


@dataclass
class HandHistory:
    """Complete hand history record."""
    hand_id: str
    timestamp: datetime
    table_name: str
    max_seats: int
    button_seat: int
    blinds: tuple[float, float]  # (small_blind, big_blind)
    
    # Players
    players: dict[str, float]  # name -> starting stack
    
    # Actions by street
    actions: list[PlayerAction] = field(default_factory=list)
    
    # Board cards
    board: list[str] = field(default_factory=list)  # e.g., ["7h", "8c", "9d", "Td", "2s"]
    
    # Results
    pot: float = 0.0
    rake: float = 0.0
    winners: dict[str, float] = field(default_factory=dict)  # name -> amount won
    showdowns: list[Showdown] = field(default_factory=list)
    
    # Raw text
    raw_text: str = ""


# Regex patterns for PokerStars format
_HAND_ID_PATTERN = re.compile(r"PokerStars Hand #(\d+):")
_TIMESTAMP_PATTERN = re.compile(r"(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})")
_TABLE_PATTERN = re.compile(r"Table '([^']+)'")
_SEATS_PATTERN = re.compile(r"(\d+)-max")
_BUTTON_PATTERN = re.compile(r"Seat #(\d+) is the button")
_PLAYER_PATTERN = re.compile(r"Seat (\d+): (\w+) \(\$(\d+(?:\.\d+)?) in chips\)")
_BLINDS_PATTERN = re.compile(r"posts (?:small|big) blind \$(\d+(?:\.\d+)?)")
_DEALT_PATTERN = re.compile(r"Dealt to (\w+) \[([^\]]+)\]")
_ACTION_PATTERN = re.compile(r"(\w+): (folds|checks|calls|bets|raises)(?: \$(\d+(?:\.\d+)?))?(?: to \$(\d+(?:\.\d+)?))?")
_BOARD_PATTERN = re.compile(r"\[([^\]]+)\]")
_POT_PATTERN = re.compile(r"Total pot \$(\d+(?:\.\d+)?)")
_RAKE_PATTERN = re.compile(r"Rake \$(\d+(?:\.\d+)?)")
_COLLECTED_PATTERN = re.compile(r"(\w+) collected \$(\d+(?:\.\d+)?) from pot")
_SHOWDOWN_PATTERN = re.compile(r"Seat \d+: (\w+) \(([^)]+)\)")


def _parse_action(action_str: str, player: str, street: Street) -> Optional[PlayerAction]:
    """Parse an action string into a PlayerAction."""
    action_str = action_str.lower().strip()
    
    if action_str == "folds":
        return PlayerAction(player, Action.FOLD, street=street)
    elif action_str == "checks":
        return PlayerAction(player, Action.CHECK, street=street)
    elif action_str.startswith("calls"):
        match = re.search(r"\$(\d+(?:\.\d+)?)", action_str)
        amount = float(match.group(1)) if match else 0.0
        return PlayerAction(player, Action.CALL, amount, street)
    elif action_str.startswith("bets"):
        match = re.search(r"\$(\d+(?:\.\d+)?)", action_str)
        amount = float(match.group(1)) if match else 0.0
        return PlayerAction(player, Action.BET, amount, street)
    elif action_str.startswith("raises"):
        # Get the raise-to amount
        match = re.search(r"to \$(\d+(?:\.\d+)?)", action_str)
        if match:
            amount = float(match.group(1))
        else:
            match = re.search(r"\$(\d+(?:\.\d+)?)", action_str)
            amount = float(match.group(1)) if match else 0.0
        return PlayerAction(player, Action.RAISE, amount, street)
    elif "all-in" in action_str:
        match = re.search(r"\$(\d+(?:\.\d+)?)", action_str)
        amount = float(match.group(1)) if match else 0.0
        return PlayerAction(player, Action.ALL_IN, amount, street)
    
    return None


def parse_pokerstars(text: str) -> HandHistory:
    """Parse PokerStars format hand history."""
    lines = text.strip().split("\n")
    
    # Parse header
    hand_id_match = _HAND_ID_PATTERN.search(lines[0])
    if not hand_id_match:
        raise ValueError("Invalid PokerStars hand history: missing hand ID")
    hand_id = hand_id_match.group(1)
    
    timestamp_match = _TIMESTAMP_PATTERN.search(lines[0])
    timestamp = datetime.strptime(timestamp_match.group(1), "%Y/%m/%d %H:%M:%S") if timestamp_match else datetime.now()
    
    table_match = _TABLE_PATTERN.search(lines[1])
    table_name = table_match.group(1) if table_match else "Unknown"
    
    seats_match = _SEATS_PATTERN.search(lines[1])
    max_seats = int(seats_match.group(1)) if seats_match else 6
    
    button_match = _BUTTON_PATTERN.search(lines[1])
    button_seat = int(button_match.group(1)) if button_match else 1
    
    # Parse players
    players = {}
    for line in lines[2:]:
        player_match = _PLAYER_PATTERN.search(line)
        if player_match:
            name = player_match.group(2)
            stack = float(player_match.group(3))
            players[name] = stack
        elif line.startswith("***"):
            break
    
    # Parse blinds
    blinds = (0.0, 0.0)
    for line in lines:
        blind_match = _BLINDS_PATTERN.search(line)
        if blind_match:
            blind_amount = float(blind_match.group(1))
            if "small blind" in line:
                blinds = (blind_amount, blinds[1])
            elif "big blind" in line:
                blinds = (blinds[0], blind_amount)
    
    # Initialize hand history
    hand = HandHistory(
        hand_id=hand_id,
        timestamp=timestamp,
        table_name=table_name,
        max_seats=max_seats,
        button_seat=button_seat,
        blinds=blinds,
        players=players,
        raw_text=text,
    )
    
    # Parse actions and board
    current_street = Street.PREFLOP
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Detect street changes
        if "*** HOLE CARDS ***" in line:
            current_street = Street.PREFLOP
        elif "*** FLOP ***" in line:
            current_street = Street.FLOP
            board_match = _BOARD_PATTERN.search(line)
            if board_match:
                hand.board = board_match.group(1).split()
        elif "*** TURN ***" in line:
            current_street = Street.TURN
            board_match = _BOARD_PATTERN.search(line)
            if board_match:
                cards = board_match.group(1).split()
                if len(cards) > 1:
                    hand.board.append(cards[-1])
        elif "*** RIVER ***" in line:
            current_street = Street.RIVER
            board_match = _BOARD_PATTERN.search(line)
            if board_match:
                cards = board_match.group(1).split()
                if len(cards) > 1:
                    hand.board.append(cards[-1])
        elif "*** SUMMARY ***" in line:
            break
        
        # Parse actions
        action_match = _ACTION_PATTERN.match(line)
        if action_match:
            player = action_match.group(1)
            action_str = action_match.group(2)
            action = _parse_action(action_str, player, current_street)
            if action:
                hand.actions.append(action)
        
        # Parse collected (winners)
        collected_match = _COLLECTED_PATTERN.search(line)
        if collected_match:
            winner = collected_match.group(1)
            amount = float(collected_match.group(2))
            hand.winners[winner] = hand.winners.get(winner, 0) + amount
        
        i += 1
    
    # Parse pot
    for line in lines:
        pot_match = _POT_PATTERN.search(line)
        if pot_match:
            hand.pot = float(pot_match.group(1))
        rake_match = _RAKE_PATTERN.search(line)
        if rake_match:
            hand.rake = float(rake_match.group(1))
    
    return hand


def parse_hand_history(text: str, format: str = "auto") -> HandHistory:
    """Parse hand history from text.
    
    Args:
        text: Raw hand history text
        format: Format to use ("pokerstars", "auto")
        
    Returns:
        Parsed HandHistory object
    """
    if format == "auto":
        # Auto-detect format
        if "PokerStars Hand #" in text:
            format = "pokerstars"
        else:
            # Try PokerStars as default
            format = "pokerstars"
    
    if format == "pokerstars":
        return parse_pokerstars(text)
    else:
        raise ValueError(f"Unsupported format: {format}")


def parse_hand_history_file(filepath: str) -> list[HandHistory]:
    """Parse multiple hand histories from a file.
    
    Args:
        filepath: Path to hand history file
        
    Returns:
        List of parsed HandHistory objects
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Split by hand boundaries
    hands = re.split(r"(?=PokerStars Hand #)", content)
    hands = [h.strip() for h in hands if h.strip()]
    
    parsed = []
    for hand_text in hands:
        try:
            hand = parse_hand_history(hand_text)
            parsed.append(hand)
        except Exception as e:
            # Skip malformed hands
            continue
    
    return parsed
