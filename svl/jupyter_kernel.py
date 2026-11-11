# svl/jupyter_kernel.py
# Jupyter Kernel for SVL (H48)
# Provides IPython kernel for SVL REPL with live verification

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import json
import sys
import os
import logging

from traitlets import Bool, Int
from traitlets.config import Config

try:
    from ipykernel.kernelbase import Kernel
    from ipykernel.kernelapp import IPKernelApp
    IPYKERNEL_AVAILABLE = True
except ImportError:
    IPYKERNEL_AVAILABLE = False
    Kernel = object
    IPKernelApp = object
    Config = object

from svl.repl import SVLRepl, ReplConfig
from svl.theorem_layer import verify_theorem_layer, TheoremVerificationConfig
from svl.syntax_layer import verify_syntax, SyntaxVerificationConfig
from svl.type_layer import verify_type, TypeVerificationConfig
from traitlets import Bool, Int


@dataclass
class SVLKernelConfig:
    """Configuration for SVL Jupyter kernel."""
    verification_enabled: bool = True
    show_timing: bool = True
    max_history: int = 1000


class SVLKernel(Kernel):
    """Jupyter kernel for SVL with live verification."""
    
    implementation = 'SVL'
    implementation_version = '0.1.0'
    language = 'svl'
    language_version = '0.1'
    language_info = {
        'name': 'svl',
        'mimetype': 'text/x.svl',
        'file_extension': '.svl',
        'codemirror_mode': 'text/x.svl',
        'pygments_lexer': 'svl'
    }
    banner = "SVL Kernel - Self-Verifying Language with Live Verification"
    
    # Traitlets config
    verification_enabled = Bool(True, config=True, help="Enable live verification").tag(config=True)
    show_timing = Bool(True, config=True, help="Show timing information").tag(config=True)
    max_history = Int(1000, config=True, help="Maximum history size").tag(config=True)
    
    def __init__(self, **kwargs):
        import logging
        self.log = logging.getLogger(__name__)
        super().__init__(**kwargs)
        
        self.svl_config = SVLKernelConfig()
        
        # Verification configs
        self.syntax_config = SyntaxVerificationConfig(
            block_size=512, use_cython=True,
            verify_golden_refs=False, run_mutation_tests=False
        )
        self.type_config = TypeVerificationConfig(
            block_size=512, use_cython=True,
            verify_golden_refs=False
        )
        self.theorem_config = TheoremVerificationConfig(
            block_size=512, use_cython=True,
            verify_syntax_first=True, verify_types_first=True,
            verify_golden_refs=False
        )
        
        self.repl = SVLRepl()
        self.execution_count = 0
        self.history = []

    def do_execute(self, code: str, silent: bool, 
                   store_history: bool = True,
                   user_expressions: Optional[Dict] = None,
                   allow_stdin: bool = False) -> Dict[str, Any]:
        """Execute SVL code in the kernel."""
        self.execution_count += 1
        
        if not code.strip():
            return {
                'status': 'ok',
                'execution_count': self.execution_count,
                'payload': [],
                'user_expressions': {}
            }

        # Run verification if enabled
        verification_result = None
        if self.svl_config.verification_enabled:
            try:
                from svl.theorem_layer import verify_theorem_layer
                result = verify_theorem_layer(code, self.theorem_config)
                verification_result = {
                    'passed': result.passed,
                    'syntax_ok': result.syntax_layer_verified,
                    'types_ok': result.type_layer_verified,
                    'theorem_ok': result.all_parities_even,
                    'errors': result.errors,
                    'warnings': result.warnings,
                    'smt_verified': result.smt_verified,
                    'smt_solver_time_ms': result.smt_solver_time_ms
                }
            except Exception as e:
                verification_result = {
                    'passed': False,
                    'errors': [str(e)]
                }

        # Execute in REPL
        try:
            self.repl.state.buffer.append(code)
            self.repl._execute_block()
            output = "Executed successfully"
            status = 'ok'
        except Exception as e:
            output = f"Error: {str(e)}"
            status = 'error'

        # Prepare response
        response = {
            'status': status,
            'execution_count': self.execution_count,
            'payload': [],
            'user_expressions': {}
        }

        if not silent:
            # Send stdout
            self.send_response(self.iopub_socket, 'stream', {
                'name': 'stdout',
                'text': output + '\n'
            })

            # Send verification results
            if verification_result:
                self.send_response(self.iopub_socket, 'stream', {
                    'name': 'stdout',
                    'text': f"\n[Verification] {'✓ PASS' if verification_result['passed'] else '✗ FAIL'}\n"
                })
                if verification_result.get('errors'):
                    for err in verification_result['errors']:
                        self.send_response(self.iopub_socket, 'stream', {
                            'name': 'stderr',
                            'text': f"  Error: {err}\n"
                        })

        if store_history:
            self.history.append({
                'code': code,
                'result': status,
                'verification': verification_result
            })

        return response

    def do_complete(self, code: str, cursor_pos: int) -> Dict[str, Any]:
        """Provide code completion."""
        # Simple completion for SVL keywords
        keywords = [
            'module', 'import', 'export', 'func', 'struct', 'type',
            'const', 'var', 'let', 'if', 'then', 'else', 'while',
            'for', 'in', 'return', 'assert', 'try', 'catch', 'throw',
            'async', 'await', 'match', 'case', 'true', 'false', 'null',
            'int', 'float', 'string', 'bool', 'void', 'never',
            'box', 'diamond', 'forall', 'where', 'as', 'box', 'diamond'
        ]
        
        matches = [k for k in keywords if k.startswith(code[cursor_pos - len(code.split()[-1]):cursor_pos] if code.split() else '')]
        
        return {
            'matches': matches,
            'cursor_start': cursor_pos - len(code.split()[-1]) if code.split() else cursor_pos,
            'cursor_end': cursor_pos,
            'metadata': {},
            'status': 'ok'
        }

    def do_inspect(self, code: str, cursor_pos: int, detail_level: int = 0) -> Dict[str, Any]:
        """Provide object inspection."""
        return {
            'status': 'ok',
            'found': False,
            'data': {},
            'metadata': {}
        }


def launch_kernel():
    """Launch the SVL Jupyter kernel."""
    if not IPYKERNEL_AVAILABLE:
        print("Error: ipykernel not installed. Install with: pip install ipykernel")
        return 1
    
    from ipykernel.kernelapp import IPKernelApp
    IPKernelApp.launch_instance(kernel_class=SVLKernel)


if __name__ == '__main__':
    # Test the kernel
    print("=== SVL Jupyter Kernel Test ===")
    
    if IPYKERNEL_AVAILABLE:
        print("ipykernel available")
        # Test basic kernel creation
        kernel = SVLKernel()
        print("Kernel created successfully")
        
        # Test execution
        test_code = 'func fact(n: int, acc: int) type int { if n == 0 then { return acc } else { return fact(n - 1, n * acc) } }'
        result = kernel.do_execute(test_code, silent=False)
        print(f"Execution result: {result['status']}")
        
        # Test completion
        completions = kernel.do_complete('fun', 3)
        print(f"Completions: {completions['matches'][:5]}")
        
        print("\n✓ SVL Jupyter Kernel test complete!")
    else:
        print("ipykernel not available - install with: pip install ipykernel")
        print("Kernel code structure is valid")