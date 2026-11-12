# svl/lsp_server.py
# Language Server Protocol for SVL (Spike S12)
# pygls-based implementation with real-time verification diagnostics

from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, field
import asyncio
import json
import sys

from lsprotocol.types import (
    TEXT_DOCUMENT_DID_OPEN, TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_CLOSE, TEXT_DOCUMENT_DID_SAVE,
    TEXT_DOCUMENT_COMPLETION, TEXT_DOCUMENT_HOVER,
    TEXT_DOCUMENT_DEFINITION, TEXT_DOCUMENT_DIAGNOSTIC,
    TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
    INITIALIZE, INITIALIZED, SHUTDOWN, EXIT,
    CompletionItem, CompletionList, CompletionParams,
    Hover, HoverParams, Location, Position, Range,
    Diagnostic, DiagnosticSeverity, PublishDiagnosticsParams,
    InitializeParams, InitializeResult, ServerCapabilities,
    TextDocumentSyncKind, TextDocumentItem, DidChangeTextDocumentParams,
    SemanticTokensParams, SemanticTokens, SemanticTokensLegend,
    SemanticTokenTypes, SemanticTokenModifiers,
)
from pygls.lsp.server import LanguageServer

from svl.syntax_layer import verify_syntax, SyntaxVerificationConfig, VerifyResult
from svl.type_layer import verify_type, TypeVerificationConfig, TypeVerifyResult
from svl.theorem_layer import verify_theorem_layer, TheoremVerificationConfig, TheoremVerifyResultWrapper
from svl.compiler_wasm import compile_file_to_wasm, wasm_sha256
from svl.lexer import tokenize
from svl.parser_rd import parse


@dataclass
class DocumentState:
    """Track document state for incremental verification."""
    uri: str
    version: int
    content: str
    ast: Optional[Any] = None
    tokens: Optional[List] = None
    last_verified_version: int = -1


class SVLLanguageServer(LanguageServer):
    """SVL Language Server with live verification."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.documents: Dict[str, DocumentState] = {}
        
        # Verification configs (fast for LSP)
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
        
        # Semantic tokens legend - use string literals for token types/modifiers
        self._semantic_tokens_legend = SemanticTokensLegend(
            token_types=[
                "keyword", "function", "variable", "parameter", "type",
                "struct", "comment", "string", "number", "operator", "modifier",
            ],
            token_modifiers=["declaration", "readonly"]
        )

    async def initialize(self, params: InitializeParams) -> InitializeResult:
        """Initialize server capabilities."""
        return InitializeResult(
            capabilities=ServerCapabilities(
                text_document_sync=TextDocumentSyncKind.Incremental,
                completion_provider={"trigger_characters": [".", ":", "("]},
                hover_provider=True,
                definition_provider=True,
                diagnostic_provider={"inter_file_dependencies": False},
                semantic_tokens_provider={
                    "legend": self._semantic_tokens_legend,
                    "full": True
                },
            ),
            server_info={"name": "svl-lsp", "version": "0.1.0"}
        )

    def did_open(self, params):
        """Handle document open."""
        doc = params.text_document
        self.documents[doc.uri] = DocumentState(
            uri=doc.uri, version=doc.version, content=doc.text
        )
        self._verify_document(doc.uri)

    def did_change(self, params: DidChangeTextDocumentParams):
        """Handle document change (incremental)."""
        uri = params.text_document.uri
        if uri not in self.documents:
            return
        
        doc_state = self.documents[uri]
        doc_state.version = params.text_document.version
        
        # Apply changes
        for change in params.content_changes:
            if hasattr(change, 'range') and change.range:
                # Incremental change - for simplicity, replace full text
                doc_state.content = change.text
            else:
                doc_state.content = change.text
        
        self._verify_document(uri)

    def did_close(self, params):
        """Handle document close."""
        uri = params.text_document.uri
        if uri in self.documents:
            del self.documents[uri]

    def did_save(self, params):
        """Handle document save - full verification."""
        uri = params.text_document.uri
        if uri in self.documents:
            self._verify_document(uri, full=True)

    def _verify_document(self, uri: str, full: bool = False):
        """Run verification and publish diagnostics."""
        doc_state = self.documents.get(uri)
        if not doc_state:
            return
        
        # Skip if already verified this version (unless full)
        if not full and doc_state.last_verified_version == doc_state.version:
            return
        
        # Parse and verify
        try:
            tokens = tokenize(doc_state.content)
            ast = parse(tokens)
            doc_state.tokens = tokens
            doc_state.ast = ast
        except Exception as e:
            self._publish_diagnostics(uri, [
                Diagnostic(
                    range=Range(start=Position(line=0, character=0), end=Position(line=0, character=0)),
                    severity=DiagnosticSeverity.Error,
                    message=f"Parse error: {e}",
                    source="svl"
                )
            ])
            return
        
        # Run verification layers
        source = doc_state.content
        diagnostics = []
        
        # Layer 1: Syntax
        syntax_result = verify_syntax(source, self.syntax_config)
        if not syntax_result.passed:
            for error in syntax_result.ast_guard_violations:
                diagnostics.append(Diagnostic(
                    range=Range(start=Position(line=0, character=0), end=Position(line=0, character=0)),
                    severity=DiagnosticSeverity.Error,
                    message=f"Syntax: {error}",
                    source="svl-syntax"
                ))
            if syntax_result.error_message:
                diagnostics.append(Diagnostic(
                    range=Range(start=Position(line=0, character=0), end=Position(line=0, character=0)),
                    severity=DiagnosticSeverity.Error,
                    message=f"Syntax: {syntax_result.error_message}",
                    source="svl-syntax"
                ))
        
        # Layer 2: Types
        type_result = verify_type(source, self.type_config)
        if not type_result.passed:
            for error in type_result.errors:
                diagnostics.append(Diagnostic(
                    range=Range(start=Position(line=0, character=0), end=Position(line=0, character=0)),
                    severity=DiagnosticSeverity.Error,
                    message=f"Type: {error}",
                    source="svl-types"
                ))
        
        # Layer 3: Theorem
        theorem_result = verify_theorem_layer(source, self.theorem_config)
        if not theorem_result.passed:
            for error in theorem_result.errors:
                diagnostics.append(Diagnostic(
                    range=Range(start=Position(line=0, character=0), end=Position(line=0, character=0)),
                    severity=DiagnosticSeverity.Warning,  # Theorem is probabilistic
                    message=f"Theorem: {error}",
                    source="svl-theorem"
                ))
        
        # Update verified version
        doc_state.last_verified_version = doc_state.version
        
        # Publish diagnostics
        self._publish_diagnostics(uri, diagnostics)

    def _publish_diagnostics(self, uri: str, diagnostics: List[Diagnostic]):
        """Publish diagnostics to client."""
        self.publish_diagnostics(PublishDiagnosticsParams(uri=uri, diagnostics=diagnostics))

    # ============================================================
    # LSP Features: Completion, Hover, Definition, Semantic Tokens
    # ============================================================

    def completion(self, params: CompletionParams) -> CompletionList:
        """Provide completions."""
        uri = params.text_document.uri
        doc_state = self.documents.get(uri)
        if not doc_state:
            return CompletionList(is_incomplete=False, items=[])
        
        # SVL keywords and built-ins
        keywords = [
            ("module", "Keyword"), ("import", "Keyword"), ("export", "Keyword"),
            ("func", "Keyword"), ("struct", "Keyword"), ("type", "Keyword"),
            ("const", "Keyword"), ("var", "Keyword"), ("let", "Keyword"),
            ("if", "Keyword"), ("then", "Keyword"), ("else", "Keyword"),
            ("while", "Keyword"), ("for", "Keyword"), ("in", "Keyword"),
            ("return", "Keyword"), ("assert", "Keyword"), ("try", "Keyword"),
            ("catch", "Keyword"), ("throw", "Keyword"), ("async", "Keyword"),
            ("await", "Keyword"), ("match", "Keyword"), ("case", "Keyword"),
            ("int", "Type"), ("float", "Type"), ("string", "Type"),
            ("bool", "Type"), ("void", "Type"), ("never", "Type"),
            ("true", "Literal"), ("false", "Literal"), ("null", "Literal"),
        ]
        
        items = [
            CompletionItem(
                label=kw,
                kind=14 if kind == "Keyword" else (7 if kind == "Type" else 15),
                detail=f"SVL {kind}"
            )
            for kw, kind in keywords
        ]
        
        # Add user-defined symbols from AST
        if doc_state.ast:
            for module in doc_state.ast.modules:
                for item in module.body.statements:
                    if hasattr(item, 'name'):
                        items.append(CompletionItem(
                            label=item.name,
                            kind=6 if isinstance(item, type(doc_state.ast.modules[0])) else 5,
                            detail="User defined"
                        ))
        
        return CompletionList(is_incomplete=False, items=items)

    def hover(self, params: HoverParams) -> Optional[Hover]:
        """Provide hover information."""
        uri = params.text_document.uri
        doc_state = self.documents.get(uri)
        if not doc_state or not doc_state.tokens:
            return None
        
        position = params.position
        # Find token at position
        for token in doc_state.tokens:
            if (token.line - 1 == position.line and 
                token.column - 1 <= position.character < token.column - 1 + len(token.value)):
                
                # Provide info based on token type
                info = self._get_token_info(token)
                if info:
                    return Hover(contents=info)
        
        return None

    def _get_token_info(self, token) -> Optional[str]:
        """Get hover info for token."""
        type_names = {
            'LET': 'Variable binding (א)', 'IF': 'Conditional (ב)',
            'THEN': 'Then branch (ג)', 'ELSE': 'Else branch (ד)',
            'WHILE': 'Loop (ה)', 'FOR': 'Iteration (ו)',
            'FUNC': 'Function definition (ז)', 'RETURN': 'Return (ח)',
            'MATCH': 'Pattern match (ט)', 'TYPE': 'Type annotation (י)',
            'STRUCT': 'Struct definition (כ)', 'MODULE': 'Module (ל)',
            'IMPORT': 'Import (מ)', 'EXPORT': 'Export (נ)',
            'CONST': 'Constant (ס)', 'VAR': 'Mutable variable (ע)',
            'ASSERT': 'Assertion (פ)', 'TRY': 'Try block (צ)',
            'CATCH': 'Catch handler (ק)', 'THROW': 'Throw (ר)',
            'ASYNC': 'Async function (ש)', 'AWAIT': 'Await (ת)',
        }
        if token.type.name in type_names:
            return f"**{token.value}** — {type_names[token.type.name]}"
        return None

    def definition(self, params) -> Optional[List[Location]]:
        """Go to definition."""
        # Simplified - would need symbol table
        return None

    def semantic_tokens_full(self, params: SemanticTokensParams) -> SemanticTokens:
        """Provide semantic tokens for syntax highlighting."""
        uri = params.text_document.uri
        doc_state = self.documents.get(uri)
        if not doc_state or not doc_state.tokens:
            return SemanticTokens(data=[])
        
        data = []
        prev_line = 0
        prev_char = 0
        
        token_type_map = {
            'LET': 0, 'IF': 0, 'THEN': 0, 'ELSE': 0, 'WHILE': 0, 'FOR': 0,
            'FUNC': 1, 'RETURN': 0, 'MATCH': 0, 'TYPE': 3, 'STRUCT': 4,
            'MODULE': 0, 'IMPORT': 0, 'EXPORT': 0, 'CONST': 5, 'VAR': 2,
            'ASSERT': 0, 'TRY': 0, 'CATCH': 0, 'THROW': 0, 'ASYNC': 0,
            'AWAIT': 0, 'MATCH': 0, 'CASE': 0,
            'INT': 8, 'FLOAT': 8, 'STRING': 7, 'BOOL': 8, 'NULL': 8,
            'IDENT': 2, 'PLUS': 9, 'MINUS': 9, 'STAR': 9, 'SLASH': 9,
            'EQ': 9, 'NE': 9, 'LT': 9, 'GT': 9, 'AND': 9, 'OR': 9,
        }
        
        for token in doc_state.tokens:
            token_type = token_type_map.get(token.type.name, 2)
            line = token.line - 1
            char = token.column - 1
            
            delta_line = line - prev_line
            delta_char = char - prev_char if delta_line == 0 else char
            
            data.extend([delta_line, delta_char, len(token.value), token_type, 0])
            
            prev_line = line
            prev_char = char
        
        return SemanticTokens(data=data)


# ============================================================
# CLI Entry Point
# ============================================================

def main():
    """Run LSP server."""
    import logging
    logging.basicConfig(level=logging.INFO)
    
    server = SVLLanguageServer("svl-lsp", "0.1.0")
    
    # Register handlers.  Pass the UNBOUND functions: `server.feature(NAME)(server.method)`
    # passes a bound method, and pygls's assign_help_attrs does setattr(f, ATTR_REGISTERED_NAME, ...)
    # which bound methods reject with
    # `AttributeError: 'method' object has no attribute 'reg_name'`.
    server.feature(INITIALIZE)(SVLLanguageServer.initialize)
    server.feature(TEXT_DOCUMENT_DID_OPEN)(SVLLanguageServer.did_open)
    server.feature(TEXT_DOCUMENT_DID_CHANGE)(SVLLanguageServer.did_change)
    server.feature(TEXT_DOCUMENT_DID_CLOSE)(SVLLanguageServer.did_close)
    server.feature(TEXT_DOCUMENT_DID_SAVE)(SVLLanguageServer.did_save)
    server.feature(TEXT_DOCUMENT_COMPLETION)(SVLLanguageServer.completion)
    server.feature(TEXT_DOCUMENT_HOVER)(SVLLanguageServer.hover)
    server.feature(TEXT_DOCUMENT_DEFINITION)(SVLLanguageServer.definition)
    server.feature(TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL)(SVLLanguageServer.semantic_tokens_full)
    
    # Run stdio server
    server.start_io()


if __name__ == '__main__':
    main()