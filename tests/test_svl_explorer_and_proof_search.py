"""AST/type explorer and automated tactic search (spikes H36 and H37).

H36 used to be a declared stub ("Visual explorer not implemented") and H37 an honest
stub too ("AI proof search not implemented").  Both now run real, reproducible code.

H37's scope is deliberately narrower than its old name: the search is deterministic
breadth-first over ``svl.tactics``, not LLM-guided, and it says so in every report.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from svl.ast_explorer import build_explorer_html
from svl.cli import main as cli_main
from svl.proof_search import describe_script, search_proof
from svl.tactics import assumption, exact, intro, trivial


class TestAstExplorer:
    def test_page_contains_the_ast_and_the_inferred_types(self):
        src = ('module m { func add(a: int, b: int) type int { return a + b } '
               ' func main() type int { return add(40, 2) } }')
        page = build_explorer_html(src)
        assert "<html" in page
        assert "FuncDecl" in page                  # AST nodes are rendered
        assert "main" in page                      # the function name appears
        assert "Inferred types" in page            # the type table is present

    def test_output_is_deterministic(self):
        src = 'module m { func f(x: int) type int { return x } }'
        assert build_explorer_html(src) == build_explorer_html(src)

    def test_source_text_is_escaped(self):
        """A string literal containing markup must not become live HTML."""
        src = 'module m { func main() type void { print("<script>alert(1)</script>") } }'
        page = build_explorer_html(src)
        assert "<script>alert(1)</script>" not in page
        assert "&lt;script&gt;" in page

    def test_a_broken_program_reports_the_error(self):
        page = build_explorer_html("module m { func main( ")
        assert "Verification problems" in page

    def test_cli_writes_a_file(self, tmp_path, capsys):
        src = tmp_path / "prog.svl"
        src.write_text("module m { func main() type int { return 42 } }")
        out = tmp_path / "page.html"
        assert cli_main(["explore", str(src), "--out", str(out)]) == 0
        page = out.read_text(encoding="utf-8")
        assert "FuncDecl" in page
        assert str(out) in capsys.readouterr().out


class TestProofSearch:
    def test_identity_implication_is_proven(self):
        result = search_proof('A -> A', [intro, trivial, assumption], max_depth=4)
        assert result.found
        assert len(result.script) == 2
        assert describe_script(result.script) == "Intro; Assumption"

    def test_an_unprovable_goal_is_reported_not_proven(self):
        """The negative control: no proof exists, so none may be reported."""
        result = search_proof('C', [intro, trivial], max_depth=3, max_nodes=50)
        assert not result.found
        assert "no proof" in result.message
        assert result.nodes_explored >= 1

    def test_the_budget_is_honoured(self):
        """A large budget cannot make an unprovable goal provable."""
        result = search_proof('Q', [intro, trivial], max_depth=2, max_nodes=8)
        assert not result.found
        assert result.nodes_explored <= 9

    def test_search_is_reproducible(self):
        a = search_proof('B -> B', [intro, trivial, assumption], max_depth=4)
        b = search_proof('B -> B', [intro, trivial, assumption], max_depth=4)
        assert a.found and b.found
        assert describe_script(a.script) == describe_script(b.script)
        assert a.nodes_explored == b.nodes_explored

    def test_exact_closes_a_matching_goal(self):
        result = search_proof('A', [exact('proof_of_A')], max_depth=1)
        assert result.found
        assert describe_script(result.script).startswith("Exact")

    def test_the_spike_suite_is_complete(self):
        """H36 and H37 both pass with real implementations."""
        from svl.spike_runner import spike_h36_visual_explorer, spike_h37_ai_proof_search
        h36 = spike_h36_visual_explorer()
        h37 = spike_h37_ai_proof_search()
        assert h36.passed, h36.error
        assert h37.passed, h37.error
        assert h37.metrics['ai_implemented'] is False, \
            "the LLM-guided variant must never be claimed without a model call"