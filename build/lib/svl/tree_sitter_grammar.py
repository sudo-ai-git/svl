# svl/tree_sitter_grammar.py
# Tree-sitter Grammar for SVL (H33)
# Provides syntax highlighting and parsing for LSP

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import json


# Tree-sitter grammar for SVL (JSON format for tree-sitter CLI)
SVL_GRAMMAR = {
    "name": "svl",
    "version": "0.1.0",
    "rules": {
        "source_file": {
            "type": "SEQ",
            "members": [{"type": "STAR", "content": "definition"}]
        },
        "definition": {
            "type": "CHOICE",
            "members": [
                "module_declaration",
                "import_declaration",
                "export_declaration",
                "function_declaration",
                "struct_declaration",
                "type_alias_declaration",
                "const_declaration",
                "var_declaration",
                "effect_declaration",
                "instance_declaration",
                "class_declaration"
            ]
        },
        "module_declaration": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "module"},
                {"type": "RULE", "name": "identifier"},
                {"type": "RULE", "name": "block"}
            ]
        },
        "import_declaration": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "import"},
                {"type": "RULE", "name": "string_literal"},
                {"type": "OPTIONAL", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "TOKEN", "value": "@"},
                        {"type": "RULE", "name": "version_constraint"}
                    ]
                }}
            ]
        },
        "export_declaration": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "export"},
                {"type": "RULE", "name": "identifier"}
            ]
        },
        "function_declaration": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "func"},
                {"type": "RULE", "name": "identifier"},
                {"type": "RULE", "name": "parameter_list"},
                {"type": "OPTIONAL", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "TOKEN", "value": "type"},
                        {"type": "RULE", "name": "type_expression"}
                    ]
                }},
                {"type": "RULE", "name": "block"}
            ]
        },
        "parameter_list": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "("},
                {"type": "STAR", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "RULE", "name": "parameter"},
                        {"type": "OPTIONAL", "content": {"type": "TOKEN", "value": ","}}
                    ]
                }},
                {"type": "TOKEN", "value": ")"}
            ]
        },
        "parameter": {
            "type": "SEQ",
            "members": [
                {"type": "RULE", "name": "identifier"},
                {"type": "OPTIONAL", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "TOKEN", "value": ":"},
                        {"type": "RULE", "name": "type_expression"}
                    ]
                }}
            ]
        },
        "struct_declaration": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "struct"},
                {"type": "RULE", "name": "identifier"},
                {"type": "RULE", "name": "struct_body"}
            ]
        },
        "struct_body": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "{"},
                {"type": "STAR", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "RULE", "name": "field_declaration"},
                        {"type": "OPTIONAL", "content": {"type": "TOKEN", "value": ","}}
                    ]
                }},
                {"type": "TOKEN", "value": "}"}
            ]
        },
        "field_declaration": {
            "type": "SEQ",
            "members": [
                {"type": "RULE", "name": "identifier"},
                {"type": "OPTIONAL", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "TOKEN", "value": ":"},
                        {"type": "RULE", "name": "type_expression"}
                    ]
                }}
            ]
        },
        "type_alias_declaration": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "type"},
                {"type": "RULE", "name": "identifier"},
                {"type": "OPTIONAL", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "TOKEN", "value": "<"},
                        {"type": "RULE", "name": "type_parameter_list"},
                        {"type": "TOKEN", "value": ">"}
                    ]
                }},
                {"type": "TOKEN", "value": "="},
                {"type": "RULE", "name": "type_expression"}
            ]
        },
        "const_declaration": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "const"},
                {"type": "RULE", "name": "identifier"},
                {"type": "OPTIONAL", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "TOKEN", "value": ":"},
                        {"type": "RULE", "name": "type_expression"}
                    ]
                }},
                {"type": "TOKEN", "value": "="},
                {"type": "RULE", "name": "expression"}
            ]
        },
        "var_declaration": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "var"},
                {"type": "RULE", "name": "identifier"},
                {"type": "OPTIONAL", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "TOKEN", "value": ":"},
                        {"type": "RULE", "name": "type_expression"}
                    ]
                }},
                {"type": "TOKEN", "value": "="},
                {"type": "RULE", "name": "expression"}
            ]
        },
        "effect_declaration": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "effect"},
                {"type": "RULE", "name": "identifier"},
                {"type": "RULE", "name": "effect_body"}
            ]
        },
        "effect_body": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "{"},
                {"type": "STAR", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "RULE", "name": "effect_operation"},
                        {"type": "TOKEN", "value": ";"}
                    ]
                }},
                {"type": "TOKEN", "value": "}"}
            ]
        },
        "effect_operation": {
            "type": "SEQ",
            "members": [
                {"type": "RULE", "name": "identifier"},
                {"type": "TOKEN", "value": "("},
                {"type": "STAR", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "RULE", "name": "parameter"},
                        {"type": "OPTIONAL", "content": {"type": "TOKEN", "value": ","}}
                    ]
                }},
                {"type": "TOKEN", "value": ")"},
                {"type": "OPTIONAL", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "TOKEN", "value": "->"},
                        {"type": "RULE", "name": "type_expression"}
                    ]
                }},
                {"type": "TOKEN", "value": ";"}
            ]
        },
        "instance_declaration": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "instance"},
                {"type": "RULE", "name": "type_expression"},
                {"type": "OPTIONAL", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "TOKEN", "value": "<"},
                        {"type": "RULE", "name": "type_argument_list"},
                        {"type": "TOKEN", "value": ">"}
                    ]
                }},
                {"type": "TOKEN", "value": "{"},
                {"type": "STAR", "content": {"type": "RULE", "name": "function_declaration"}},
                {"type": "TOKEN", "value": "}"}
            ]
        },
        "class_declaration": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "class"},
                {"type": "RULE", "name": "identifier"},
                {"type": "OPTIONAL", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "TOKEN", "value": "<"},
                        {"type": "RULE", "name": "type_parameter_list"},
                        {"type": "TOKEN", "value": ">"}
                    ]
                }},
                {"type": "TOKEN", "value": "where"},
                {"type": "RULE", "name": "constraint_list"},
                {"type": "RULE", "name": "class_body"}
            ]
        },
        "class_body": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "{"},
                {"type": "STAR", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "RULE", "name": "class_method"},
                        {"type": "OPTIONAL", "content": {"type": "TOKEN", "value": ";"}}
                    ]
                }},
                {"type": "TOKEN", "value": "}"}
            ]
        },
        "class_method": {
            "type": "SEQ",
            "members": [
                {"type": "RULE", "name": "identifier"},
                {"type": "TOKEN", "value": "("},
                {"type": "STAR", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "RULE", "name": "parameter"},
                        {"type": "OPTIONAL", "content": {"type": "TOKEN", "value": ","}}
                    ]
                }},
                {"type": "TOKEN", "value": ")"},
                {"type": "OPTIONAL", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "TOKEN", "value": "->"},
                        {"type": "RULE", "name": "type_expression"}
                    ]
                }},
                {"type": "TOKEN", "value": "{"},
                {"type": "RULE", "name": "block"}
            ]
        },
        "block": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "{"},
                {"type": "STAR", "content": "statement"},
                {"type": "TOKEN", "value": "}"}
            ]
        },
        "statement": {
            "type": "CHOICE",
            "members": [
                "let_statement",
                "if_statement",
                "while_statement",
                "for_statement",
                "return_statement",
                "assert_statement",
                "try_statement",
                "expression_statement",
                "block"
            ]
        },
        "let_statement": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "let"},
                {"type": "RULE", "name": "identifier"},
                {"type": "OPTIONAL", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "TOKEN", "value": ":"},
                        {"type": "RULE", "name": "type_expression"}
                    ]
                }},
                {"type": "TOKEN", "value": "="},
                {"type": "RULE", "name": "expression"}
            ]
        },
        "if_statement": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "if"},
                {"type": "RULE", "name": "expression"},
                {"type": "TOKEN", "value": "then"},
                {"type": "RULE", "name": "block"},
                {"type": "OPTIONAL", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "TOKEN", "value": "else"},
                        {"type": "RULE", "name": "block"}
                    ]
                }}
            ]
        },
        "while_statement": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "while"},
                {"type": "RULE", "name": "expression"},
                {"type": "RULE", "name": "block"}
            ]
        },
        "for_statement": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "for"},
                {"type": "RULE", "name": "identifier"},
                {"type": "TOKEN", "value": "in"},
                {"type": "RULE", "name": "expression"},
                {"type": "RULE", "name": "block"}
            ]
        },
        "return_statement": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "return"},
                {"type": "OPTIONAL", "content": {"type": "RULE", "name": "expression"}}
            ]
        },
        "assert_statement": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "assert"},
                {"type": "RULE", "name": "expression"}
            ]
        },
        "try_statement": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "try"},
                {"type": "RULE", "name": "block"},
                {"type": "TOKEN", "value": "catch"},
                {"type": "RULE", "name": "identifier"},
                {"type": "OPTIONAL", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "TOKEN", "value": ":"},
                        {"type": "RULE", "name": "type_expression"}
                    ]
                }},
                {"type": "RULE", "name": "block"}
            ]
        },
        "expression_statement": {
            "type": "SEQ",
            "members": [
                {"type": "RULE", "name": "expression"}
            ]
        },
        "expression": {
            "type": "CHOICE",
            "members": [
                "literal",
                "identifier",
                "call_expression",
                "binary_expression",
                "unary_expression",
                "struct_literal",
                "array_literal",
                "cast_expression",
                "if_expression",
                "match_expression",
                "lambda_expression"
            ]
        },
        "literal": {
            "type": "CHOICE",
            "members": [
                {"type": "RULE", "name": "integer_literal"},
                {"type": "RULE", "name": "float_literal"},
                {"type": "RULE", "name": "string_literal"},
                {"type": "RULE", "name": "boolean_literal"},
                {"type": "RULE", "name": "null_literal"}
            ]
        },
        "integer_literal": {
            "type": "TOKEN",
            "value": "[0-9]+"
        },
        "float_literal": {
            "type": "TOKEN",
            "value": "[0-9]+\\.[0-9]+"
        },
        "string_literal": {
            "type": "TOKEN",
            "value": "\"[^\"]*\""
        },
        "boolean_literal": {
            "type": "CHOICE",
            "members": [
                {"type": "TOKEN", "value": "true"},
                {"type": "TOKEN", "value": "false"}
            ]
        },
        "null_literal": {
            "type": "TOKEN",
            "value": "null"
        },
        "identifier": {
            "type": "TOKEN",
            "value": "[a-zA-Z_][a-zA-Z0-9_]*"
        },
        "type_expression": {
            "type": "CHOICE",
            "members": [
                "primitive_type",
                "struct_type",
                "function_type",
                "generic_type",
                "tuple_type",
                "array_type",
                "refinement_type",
                "forall_type",
                "box_type",
                "diamond_type",
                "kind_star"
            ]
        },
        "primitive_type": {
            "type": "CHOICE",
            "members": [
                {"type": "TOKEN", "value": "int"},
                {"type": "TOKEN", "value": "float"},
                {"type": "TOKEN", "value": "string"},
                {"type": "TOKEN", "value": "bool"},
                {"type": "TOKEN", "value": "void"},
                {"type": "TOKEN", "value": "never"}
            ]
        },
        "struct_type": {
            "type": "RULE",
            "name": "identifier"
        },
        "function_type": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "fn"},
                {"type": "TOKEN", "value": "("},
                {"type": "STAR", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "RULE", "name": "type_expression"},
                        {"type": "OPTIONAL", "content": {"type": "TOKEN", "value": ","}}
                    ]
                }},
                {"type": "TOKEN", "value": ")"},
                {"type": "TOKEN", "value": "->"},
                {"type": "RULE", "name": "type_expression"}
            ]
        },
        "generic_type": {
            "type": "SEQ",
            "members": [
                {"type": "RULE", "name": "identifier"},
                {"type": "TOKEN", "value": "<"},
                {"type": "STAR", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "RULE", "name": "type_expression"},
                        {"type": "OPTIONAL", "content": {"type": "TOKEN", "value": ","}}
                    ]
                }},
                {"type": "TOKEN", "value": ">"}
            ]
        },
        "tuple_type": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "("},
                {"type": "STAR", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "RULE", "name": "type_expression"},
                        {"type": "OPTIONAL", "content": {"type": "TOKEN", "value": ","}}
                    ]
                }},
                {"type": "TOKEN", "value": ")"}
            ]
        },
        "array_type": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "["},
                {"type": "RULE", "name": "type_expression"},
                {"type": "TOKEN", "value": "]"}
            ]
        },
        "refinement_type": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "{"},
                {"type": "RULE", "name": "identifier"},
                {"type": "TOKEN", "value": ":"},
                {"type": "RULE", "name": "type_expression"},
                {"type": "TOKEN", "value": "|"},
                {"type": "RULE", "name": "expression"},
                {"type": "TOKEN", "value": "}"}
            ]
        },
        "forall_type": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "forall"},
                {"type": "STAR", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "RULE", "name": "identifier"},
                        {"type": "OPTIONAL", "content": {"type": "TOKEN", "value": ","}}
                    ]
                }},
                {"type": "OPTIONAL", "content": {"type": "TOKEN", "value": "."}},
                {"type": "RULE", "name": "constraint_list"},
                {"type": "TOKEN", "value": "=>"},
                {"type": "RULE", "name": "type_expression"}
            ]
        },
        "constraint_list": {
            "type": "STAR",
            "content": {
                "type": "SEQ",
                "members": [
                    {"type": "RULE", "name": "type_expression"},
                    {"type": "OPTIONAL", "content": {"type": "TOKEN", "value": ","}}
                ]
            }
        },
        "box_type": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "box"},
                {"type": "RULE", "name": "type_expression"}
            ]
        },
        "diamond_type": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "diamond"},
                {"type": "RULE", "name": "type_expression"}
            ]
        },
        "kind_star": {
            "type": "TOKEN",
            "value": "\\*"
        },
        "call_expression": {
            "type": "SEQ",
            "members": [
                {"type": "RULE", "name": "identifier"},
                {"type": "TOKEN", "value": "("},
                {"type": "STAR", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "RULE", "name": "expression"},
                        {"type": "OPTIONAL", "content": {"type": "TOKEN", "value": ","}}
                    ]
                }},
                {"type": "TOKEN", "value": ")"}
            ]
        },
        "binary_expression": {
            "type": "SEQ",
            "members": [
                {"type": "RULE", "name": "expression"},
                {"type": "CHOICE", "members": [
                    {"type": "TOKEN", "value": "+"},
                    {"type": "TOKEN", "value": "-"},
                    {"type": "TOKEN", "value": "*"},
                    {"type": "TOKEN", "value": "/"},
                    {"type": "TOKEN", "value": "%"},
                    {"type": "TOKEN", "value": "=="},
                    {"type": "TOKEN", "value": "!="},
                    {"type": "TOKEN", "value": "<"},
                    {"type": "TOKEN", "value": ">"},
                    {"type": "TOKEN", "value": "<="},
                    {"type": "TOKEN", "value": ">="},
                    {"type": "TOKEN", "value": "&&"},
                    {"type": "TOKEN", "value": "||"},
                    {"type": "TOKEN", "value": "&"},
                    {"type": "TOKEN", "value": "|"},
                    {"type": "TOKEN", "value": "^"},
                    {"type": "TOKEN", "value": "<<"},
                    {"type": "TOKEN", "value": ">>"}
                ]},
                {"type": "RULE", "name": "expression"}
            ]
        },
        "unary_expression": {
            "type": "SEQ",
            "members": [
                {"type": "CHOICE", "members": [
                    {"type": "TOKEN", "value": "-"},
                    {"type": "TOKEN", "value": "!"},
                    {"type": "TOKEN", "value": "~"}
                ]},
                {"type": "RULE", "name": "expression"}
            ]
        },
        "struct_literal": {
            "type": "SEQ",
            "members": [
                {"type": "RULE", "name": "identifier"},
                {"type": "TOKEN", "value": "{"},
                {"type": "STAR", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "RULE", "name": "field_init"},
                        {"type": "OPTIONAL", "content": {"type": "TOKEN", "value": ","}}
                    ]
                }},
                {"type": "TOKEN", "value": "}"}
            ]
        },
        "field_init": {
            "type": "SEQ",
            "members": [
                {"type": "RULE", "name": "identifier"},
                {"type": "TOKEN", "value": ":"},
                {"type": "RULE", "name": "expression"}
            ]
        },
        "array_literal": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "["},
                {"type": "STAR", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "RULE", "name": "expression"},
                        {"type": "OPTIONAL", "content": {"type": "TOKEN", "value": ","}}
                    ]
                }},
                {"type": "TOKEN", "value": "]"}
            ]
        },
        "cast_expression": {
            "type": "SEQ",
            "members": [
                {"type": "RULE", "name": "expression"},
                {"type": "TOKEN", "value": "as"},
                {"type": "RULE", "name": "type_expression"}
            ]
        },
        "if_expression": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "if"},
                {"type": "RULE", "name": "expression"},
                {"type": "TOKEN", "value": "then"},
                {"type": "RULE", "name": "expression"},
                {"type": "TOKEN", "value": "else"},
                {"type": "RULE", "name": "expression"}
            ]
        },
        "match_expression": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "match"},
                {"type": "RULE", "name": "expression"},
                {"type": "TOKEN", "value": "{"},
                {"type": "STAR", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "RULE", "name": "match_case"},
                        {"type": "TOKEN", "value": ";"}
                    ]
                }},
                {"type": "TOKEN", "value": "}"}
            ]
        },
        "match_case": {
            "type": "SEQ",
            "members": [
                {"type": "RULE", "name": "pattern"},
                {"type": "TOKEN", "value": "=>"},
                {"type": "RULE", "name": "expression"}
            ]
        },
        "pattern": {
            "type": "CHOICE",
            "members": [
                "literal_pattern",
                "identifier_pattern",
                "wildcard_pattern",
                "struct_pattern"
            ]
        },
        "literal_pattern": {
            "type": "RULE",
            "name": "literal"
        },
        "identifier_pattern": {
            "type": "RULE",
            "name": "identifier"
        },
        "wildcard_pattern": {
            "type": "TOKEN",
            "value": "_"
        },
        "struct_pattern": {
            "type": "SEQ",
            "members": [
                {"type": "RULE", "name": "identifier"},
                {"type": "TOKEN", "value": "{"},
                {"type": "STAR", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "RULE", "name": "field_pattern"},
                        {"type": "OPTIONAL", "content": {"type": "TOKEN", "value": ","}}
                    ]
                }},
                {"type": "TOKEN", "value": "}"}
            ]
        },
        "field_pattern": {
            "type": "SEQ",
            "members": [
                {"type": "RULE", "name": "identifier"},
                {"type": "OPTIONAL", "content": {
                    "type": "SEQ",
                    "members": [
                        {"type": "TOKEN", "value": ":"},
                        {"type": "RULE", "name": "pattern"}
                    ]
                }}
            ]
        },
        "lambda_expression": {
            "type": "SEQ",
            "members": [
                {"type": "TOKEN", "value": "\\\\"},
                {"type": "RULE", "name": "parameter_list"},
                {"type": "TOKEN", "value": "->"},
                {"type": "RULE", "name": "expression"}
            ]
        },
        "version_constraint": {
            "type": "CHOICE",
            "members": [
                {"type": "TOKEN", "value": "^"},
                {"type": "TOKEN", "value": "~"},
                {"type": "TOKEN", "value": ">="},
                {"type": "TOKEN", "value": "<="},
                {"type": "TOKEN", "value": ">"},
                {"type": "TOKEN", "value": "<"},
                {"type": "TOKEN", "value": "="}
            ]
        }
    }
}


def save_grammar_to_file(filepath: str = "svl_grammar.json"):
    """Save the SVL grammar to a JSON file for tree-sitter."""
    with open(filepath, 'w') as f:
        json.dump(SVL_GRAMMAR, f, indent=2)
    print(f"Grammar saved to {filepath}")


def generate_highlight_queries() -> Dict[str, str]:
    """Generate tree-sitter highlight queries for syntax highlighting."""
    return {
        "highlights.scm": """
; SVL syntax highlighting queries
; Keywords
(keyword) @keyword
(module) @keyword
(import) @keyword
(export) @keyword
(func) @keyword
(struct) @keyword
(type) @keyword
(const) @keyword
(var) @keyword
(let) @keyword
(if) @keyword
(then) @keyword
(else) @keyword
(while) @keyword
(for) @keyword
(in) @keyword
(return) @keyword
(assert) @keyword
(try) @keyword
(catch) @keyword
(throw) @keyword
(async) @keyword
(await) @keyword
(match) @keyword
(case) @keyword
(box) @keyword
(diamond) @keyword
(forall) @keyword
(where) @keyword
(class) @keyword
(instance) @keyword
(effect) @keyword
(handle) @keyword
(with) @keyword

; Types
(primitive_type) @type
(type_expression) @type
(struct_type) @type
(generic_type) @type
(function_type) @type
(tuple_type) @type
(array_type) @type
(refinement_type) @type
(forall_type) @type
(box_type) @type
(diamond_type) @type
(kind_star) @type

; Literals
(integer_literal) @number
(float_literal) @number.float
(string_literal) @string
(boolean_literal) @boolean
(null_literal) @constant

; Functions
(func) @function
(function_declaration) @function
(call_expression) @function.call

; Variables
(identifier) @variable
(parameter) @variable.parameter

; Operators
(operator) @operator

; Comments
(comment) @comment

; Punctuation
(punctuation) @punctuation
""",
        "injections.scm": """
; No injections for SVL
""",
        "locals.scm": """
; Local variable scoping for SVL
(function_declaration
  (identifier) @local
  (parameter_list
    (parameter
      (identifier) @local)))

(lambda_expression
  (parameter_list
    (parameter
      (identifier) @local)))

(let_statement
  (identifier) @local)
""",
    }


if __name__ == '__main__':
    save_grammar_to_file()
    queries = generate_highlight_queries()
    for name, content in queries.items():
        with open(f"queries/{name}", 'w') as f:
            f.write(content)
    print("Grammar and queries saved!")