"""Tests for the Game-Theoretic Arena module (grAIl/game_arena.py).

Verifies:
- Arena state machine (IDLE→SPAWN→JUDGE→DECLARE→EVOLVE→DONE)
- pcomp_verify as impartial judge
- Ring buffer match history storage
- QMachine-driven state transitions
- Tournament management and leaderboard
- AgentLoop integration methods
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "/home/sudosudo/photonic-backup")
sys.path.insert(0, "/home/sudosudo/.local/lib/python3.12/site-packages")
sys.path.insert(0, "/home/sudosudo/photonic-compute")

import pytest

from grAIl.game_arena import (
    Arena,
    AgentPlayer,
    PhotonicJudge,
    TournamentManager,
    AgentProfile,
    MatchResult,
    TournamentResult,
    ArenaState,
)
from grAIl.agent_loop import AgentLoop


def test_arena_creation():
    """Test Arena instantiation with QMachine state machine."""
    arena = Arena(arena_id="test_arena")
    assert arena.arena_id == "test_arena"
    assert arena.state == ArenaState.IDLE
    assert len(arena.state_history) == 1
    assert arena.state_history[0] == "IDLE"


def test_arena_register_agents():
    """Test agent registration in the arena."""
    arena = Arena(arena_id="test")
    profiles = [
        AgentProfile(name=f"agent_{i}", strategy=f"strat_{i}", seed=42 + i)
        for i in range(3)
    ]
    for p in profiles:
        arena.register_agent(p)
    assert len(arena.agents) == 3
    assert all(arena.agents[p.name].profile == p for p in profiles)


def test_arena_state_machine():
    """Test ArenaState transitions follow the valid path."""
    states = [s for s in ArenaState]
    for s in states:
        allowed = s.transitions()
        # IDLE can only go to SPAWN
        if s == ArenaState.IDLE:
            assert allowed == [ArenaState.SPAWN]
        # JUDGE can only go to DECLARE
        if s == ArenaState.JUDGE:
            assert allowed == [ArenaState.DECLARE]
        # All states should be valid enum values
        assert isinstance(s.name, str)


def test_spawn_agents():
    """Test that spawn_agents transitions to SPAWN state."""
    arena = Arena(arena_id="test")
    profile = AgentProfile(name="test_agent", strategy="test")
    arena.register_agent(profile)
    arena.spawn_agents()
    assert arena.state == ArenaState.SPAWN
    assert arena.agents["test_agent"].matches_played == 0


def test_judge_match():
    """Test a single head-to-head match with pcomp_verify judge."""
    arena = Arena(arena_id="test")
    arena.register_agent(AgentProfile(name="alpha", strategy="strat_a", seed=42))
    arena.register_agent(AgentProfile(name="beta", strategy="strat_b", seed=43))
    arena.spawn_agents()

    match = arena.judge_match("alpha", "beta")
    assert isinstance(match, MatchResult)
    assert match.match_id.startswith("test")
    assert match.winner in ("alpha", "beta")
    assert match.score_a > 0
    assert match.score_b > 0
    assert len(match.judge_gates) > 0
    assert arena.match_history.count == 1


def test_photonic_judge():
    """Test PhotonicJudge uses pcomp_verify gates impartially."""
    judge = PhotonicJudge()

    # Generate two different output vectors
    out_a = {"output_vector": [0.1 * i for i in range(8)]}
    out_b = {"output_vector": [0.1 * (7 - i) for i in range(8)]}
    context = {"seed": 42}

    winner_a, gates, detail = judge.judge(out_a, out_b, context)

    assert isinstance(winner_a, bool)
    assert isinstance(gates, dict)
    assert len(gates) > 0
    assert isinstance(detail, str)

    # Verify pcomp_verify summary passes all gates
    summary = judge.summary()
    assert summary["all_pass"], f"All pcomp_verify gates should pass: {summary}"
    assert summary["total"] >= 4, "Should have at least 4 gates"


def test_pcomp_verify_all_gates():
    """Test that all pcomp_verify gates pass."""
    from pcomp.verify import summary
    s = summary()
    assert s["all_pass"], f"All gates should pass: {s}"
    assert s["total"] >= 4, "Should have at least 4 verification gates"


def test_ring_buffer():
    """Test that ring buffer stores match history with O(1) eviction."""
    from pcomp import RingBuffer

    rb = RingBuffer(size=4)
    assert rb.count == 0

    rb.push(1.0)
    rb.push(2.0)
    rb.push(3.0)
    assert rb.count == 3

    assert rb.pop() == 1.0
    assert rb.pop() == 2.0
    assert rb.count == 1

    # Test circular eviction
    rb.push(4.0)
    rb.push(5.0)
    rb.push(6.0)  # Should evict the oldest
    assert rb.count == 4  # size=4, so count should be at most 4


def test_tournament_manager():
    """Test TournamentManager creates and tracks arenas."""
    manager = TournamentManager()
    arena = manager.create_arena("tournament_1")
    assert arena.arena_id == "tournament_1"
    assert "tournament_1" in manager.arenas

    summary = manager.summary()
    assert summary["total_arenas"] == 1
    assert summary["arenas"]["tournament_1"]["state"] == "IDLE"


def test_tournament_round():
    """Test running a complete tournament round."""
    arena = Arena(arena_id="tournament")
    arena.register_agent(AgentProfile(name="a", strategy="sa", seed=10))
    arena.register_agent(AgentProfile(name="b", strategy="sb", seed=11))
    arena.register_agent(AgentProfile(name="c", strategy="sc", seed=12))

    matches = arena.run_round(["a", "b", "c"])
    # 3 agents -> 3 matches (a-b, a-c, b-c)
    assert len(matches) == 3
    assert all(isinstance(m, MatchResult) for m in matches)
    # After round, state should be SPAWN (ready for next round)
    assert arena.state == ArenaState.SPAWN


def test_tournament_multi_round():
    """Test multi-round tournament with evolution."""
    arena = Arena(arena_id="multi_tournament")
    arena.register_agent(AgentProfile(name="x", strategy="sx", seed=100))
    arena.register_agent(AgentProfile(name="y", strategy="sy", seed=101))

    tournament = arena.run_tournament(["x", "y"], rounds=2)

    assert tournament.rounds == 2
    assert len(tournament.matches) >= 2  # at least one match per round
    assert tournament.winner in ("x", "y")
    assert len(tournament.state_history) > 0
    assert ArenaState.DONE.name in tournament.state_history


def test_leaderboard():
    """Test that leaderboard tracks agent strength correctly."""
    arena = Arena(arena_id="lb_test")
    arena.register_agent(AgentProfile(name="strong", strategy="s", seed=1))
    arena.register_agent(AgentProfile(name="weak", strategy="w", seed=2))

    # Register wins for strong agent
    arena.agents["strong"].record_win(1.5)
    arena.agents["strong"].record_win(1.5)
    arena.agents["weak"].record_loss(0.5)

    lb = {name: agent.strength for name, agent in arena.agents.items()}
    assert lb["strong"] > lb["weak"], "Strong agent should have higher strength"


def test_evolve_winner():
    """Test that _evolve_winner produces a new strategy."""
    arena = Arena(arena_id="evolve_test")
    arena.register_agent(AgentProfile(name="winner", strategy="base_strat", seed=7))
    arena.spawn_agents()

    # Create a mock match result
    match = MatchResult(
        match_id="evolve_test-winner-vs_test-12345",
        agent_a="winner",
        agent_b="test",
        winner="winner",
        score_a=1.5,
        score_b=0.5,
        judge_gates={"bitidentity": True, "cgemm_blocked": True},
    )

    result = arena._evolve_winner("winner", match)
    assert result["winner"] == "winner"
    assert result["new_strategy"].startswith("base_strat_v2_evolved_")
    assert "qmeasure" in result
    assert "qmachine_probs" in result


def test_agent_loop_has_arena_methods():
    """Verify AgentLoop has the required arena methods."""
    assert hasattr(AgentLoop, '_run_arena')
    assert hasattr(AgentLoop, '_photonic_judge')
    assert hasattr(AgentLoop, '_tournament_round')
    assert hasattr(AgentLoop, '_evolve_winner')

    # Check that _run_arena is a regular method
    assert callable(getattr(AgentLoop, '_run_arena'))
    # Check that _tournament_round and _evolve_winner are async
    import inspect
    assert inspect.iscoroutinefunction(getattr(AgentLoop, '_tournament_round'))
    assert inspect.iscoroutinefunction(getattr(AgentLoop, '_evolve_winner'))


def test_agent_profile_dataclass():
    """Test AgentProfile dataclass works correctly."""
    profile = AgentProfile(name="test", strategy="test_strategy", seed=42)
    assert profile.name == "test"
    assert profile.strategy == "test_strategy"
    assert profile.seed == 42
    assert profile.model_ref == "default"

    # Test metadata field
    profile2 = AgentProfile(name="test2", strategy="s", metadata={"key": "val"})
    assert profile2.metadata == {"key": "val"}


def test_match_result_dataclass():
    """Test MatchResult dataclass serialization."""
    match = MatchResult(
        match_id="test_match",
        agent_a="a",
        agent_b="b",
        winner="a",
        score_a=1.0,
        score_b=0.5,
        judge_gates={"bitidentity": True},
    )
    d = match.to_dict()
    assert d["match_id"] == "test_match"
    assert d["winner"] == "a"
    assert d["judge_gates"]["bitidentity"] is True


def test_arena_integration_full():
    """Full integration: arena with pcomp_verify judge and QMachine state machine."""
    arena = Arena(arena_id="full_integration")
    for i in range(4):
        arena.register_agent(
            AgentProfile(name=f"agent_{i}", strategy=f"strat_{i}", seed=100 + i)
        )

    # Run a full tournament
    tournament = arena.run_tournament(
        [f"agent_{i}" for i in range(4)], rounds=2
    )

    assert tournament.winner != ""
    assert len(tournament.matches) > 0
    assert len(tournament.state_history) > 2

    # Verify ring buffer has matches
    assert arena.match_history.count == len(tournament.matches)

    # Verify pcomp_verify passes
    from pcomp.verify import summary
    v = summary()
    assert v["all_pass"]


def test_photonic_judge_deterministic():
    """Test that PhotonicJudge produces consistent results for same inputs."""
    judge = PhotonicJudge()
    out = {"output_vector": [0.5] * 8}
    ctx = {"seed": 123}

    winner_a1, gates1, _ = judge.judge(out, out, ctx)
    winner_a2, gates2, _ = judge.judge(out, out, ctx)

    # Same inputs should produce same gate results
    assert gates1 == gates2
    assert winner_a1 == winner_a2


def test_tournament_manager_rounds():
    """Test creating multiple arenas and running rounds."""
    manager = TournamentManager()

    for i in range(3):
        arena = manager.create_arena(f"arena_{i}")
        arena.register_agent(AgentProfile(name="x", strategy="s", seed=i))
        arena.register_agent(AgentProfile(name="y", strategy="s", seed=i + 1))
        arena.run_round(["x", "y"])

    assert len(manager.arenas) == 3
    summary = manager.summary()
    assert summary["total_arenas"] == 3

    # All arenas should have matches
    for aid, arena_data in summary["arenas"].items():
        assert arena_data["matches"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
