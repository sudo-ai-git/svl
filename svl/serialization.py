# svl/serialization.py
# AST Serialization for Spike S3
# JSON, msgpack, custom binary formats

import json
import msgpack
import struct
from typing import Any, Dict, List, Union, Optional
from dataclasses import is_dataclass, asdict, fields
from enum import Enum
from svl.parser_rd import ASTNode, NodeType
from svl.type_inference import Type, TypeVar


def ast_to_dict(node: Any) -> Any:
    """Convert AST node to dictionary recursively."""
    if node is None:
        return None
    if isinstance(node, Type):
        result = {'_type': 'Type', 'kind': node.kind, 'args': [ast_to_dict(a) for a in node.args]}
        if node.name is not None:
            result['name'] = node.name
        if node.mod5_bucket is not None:
            result['mod5_bucket'] = node.mod5_bucket.name
        if node.structural_checksum is not None:
            result['structural_checksum'] = node.structural_checksum
        return result
    if isinstance(node, TypeVar):
        return {'_type': 'TypeVar', 'name': node.name, 'id': node.id}
    if is_dataclass(node):
        result = {'_type': node.__class__.__name__}
        for f in fields(node):
            value = getattr(node, f.name)
            result[f.name] = ast_to_dict(value)
        return result
    elif isinstance(node, list):
        return [ast_to_dict(item) for item in node]
    elif isinstance(node, dict):
        return {k: ast_to_dict(v) for k, v in node.items()}
    elif isinstance(node, Enum):
        return node.value
    else:
        return node


def dict_to_ast(data: Any) -> Any:
    """Convert dictionary back to AST node."""
    if data is None:
        return None
    if isinstance(data, list):
        return [dict_to_ast(item) for item in data]
    if isinstance(data, dict):
        if '_type' in data:
            # This would need a registry of node types
            # For now, return as dict
            return {k: dict_to_ast(v) for k, v in data.items()}
        return {k: dict_to_ast(v) for k, v in data.items()}
    return data


def to_json(ast: Any, indent: int = 2) -> str:
    """Serialize AST to JSON string."""
    return json.dumps(ast_to_dict(ast), indent=indent, ensure_ascii=False)


def from_json(json_str: str) -> Any:
    """Deserialize AST from JSON string."""
    return dict_to_ast(json.loads(json_str))


def to_msgpack(ast: Any) -> bytes:
    """Serialize AST to msgpack bytes."""
    return msgpack.packb(ast_to_dict(ast), use_bin_type=True)


def from_msgpack(data: bytes) -> Any:
    """Deserialize AST from msgpack bytes."""
    return dict_to_ast(msgpack.unpackb(data, raw=False))


# ===== Custom Binary Format =====

class BinarySerializer:
    """Custom binary serialization with LEB128 integers and length-prefixed strings."""

    @staticmethod
    def encode_leb128(n: int) -> bytes:
        """Encode unsigned integer as LEB128."""
        if n < 0:
            raise ValueError("Negative numbers not supported")
        result = bytearray()
        while n >= 0x80:
            result.append((n & 0x7F) | 0x80)
            n >>= 7
        result.append(n)
        return bytes(result)

    @staticmethod
    def decode_leb128(data: bytes, offset: int = 0) -> tuple[int, int]:
        """Decode LEB128 integer. Returns (value, new_offset)."""
        result = 0
        shift = 0
        while True:
            if offset >= len(data):
                raise ValueError("Unexpected end of data")
            b = data[offset]
            offset += 1
            result |= (b & 0x7F) << shift
            if (b & 0x80) == 0:
                break
            shift += 7
        return result, offset

    @staticmethod
    def encode_string(s: str) -> bytes:
        """Encode string as length-prefixed UTF-8."""
        utf8 = s.encode('utf-8')
        return BinarySerializer.encode_leb128(len(utf8)) + utf8

    @staticmethod
    def decode_string(data: bytes, offset: int = 0) -> tuple[str, int]:
        """Decode length-prefixed string. Returns (string, new_offset)."""
        length, offset = BinarySerializer.decode_leb128(data, offset)
        if offset + length > len(data):
            raise ValueError("String length exceeds data")
        s = data[offset:offset+length].decode('utf-8')
        return s, offset + length


class ASTBinarySerializer:
    """Serialize AST nodes to custom binary format."""

    # Node type tags (1 byte each)
    NODE_TAGS = {
        'Program': 0x01,
        'Module': 0x02,
        'Import': 0x03,
        'Export': 0x04,
        'FuncDecl': 0x05,
        'StructDecl': 0x06,
        'TypeAlias': 0x07,
        'ConstDecl': 0x08,
        'VarDecl': 0x09,
        'Block': 0x0A,
        'LetStmt': 0x0B,
        'IfStmt': 0x0C,
        'WhileStmt': 0x0D,
        'ForStmt': 0x0E,
        'ReturnStmt': 0x0F,
        'AssertStmt': 0x10,
        'TryStmt': 0x11,
        'ExprStmt': 0x12,
        'BinaryExpr': 0x13,
        'UnaryExpr': 0x14,
        'CallExpr': 0x15,
        'MatchExpr': 0x16,
        'AwaitExpr': 0x17,
        'LambdaExpr': 0x18,
        'StructLit': 0x19,
        'ArrayLit': 0x1A,
        'Ident': 0x1B,
        'Literal': 0x1C,
        'CaseClause': 0x1D,
        'Pattern': 0x1E,
        'FieldPattern': 0x1F,
        'FieldInit': 0x20,
        'Param': 0x21,
        'Field': 0x22,
        'TypeExpr': 0x23,
        'FuncTypeDetail': 0x24,
        'Type': 0x25,
        'TypeVar': 0x26,
        'FieldAccess': 0x27,
        'IndexExpr': 0x28,
        'TernaryExpr': 0x29,
        'AssignExpr': 0x2A,
    }

    TAG_TO_NODE = {v: k for k, v in NODE_TAGS.items()}

    # Literal type tags
    LITERAL_TAGS = {
        'int': 0x01,
        'float': 0x02,
        'string': 0x03,
        'bool': 0x04,
        'null': 0x05,
    }

    def __init__(self, canonical: bool = False):
        self.serializer = BinarySerializer()
        # canonical=True omits source-position fields, giving a *program identity* form.
        self.canonical = canonical

    def serialize(self, node: Any) -> bytes:
        """Serialize AST node to binary."""
        if node is None:
            return b'\x00'  # Null marker
        if isinstance(node, Type):
            return self._serialize_type(node)
        if isinstance(node, TypeVar):
            return self._serialize_type_var(node)
        if is_dataclass(node):
            return self._serialize_node(node)
        elif isinstance(node, list):
            return self._serialize_list(node)
        elif isinstance(node, Enum):
            val = node.value
            if isinstance(val, str):
                return self.serializer.encode_string(val)
            else:
                return self.serializer.encode_leb128(val)
        else:
            return self._serialize_primitive(node)

    def _serialize_node(self, node: Any) -> bytes:
        node_type = node.__class__.__name__
        
        # Handle Type and TypeVar specially
        if isinstance(node, Type):
            return self._serialize_type(node)
        if isinstance(node, TypeVar):
            return self._serialize_type_var(node)
        
        tag = self.NODE_TAGS.get(node_type)
        if tag is None:
            raise ValueError(f"Unknown node type: {node_type}")

        result = bytearray([tag])

        # Serialize fields in deterministic order (sorted by field name).
        # The canonical form omits source positions: they are layout, not program identity.
        for f in sorted(fields(node), key=lambda x: x.name):
            if self.canonical and f.name in POSITION_FIELDS:
                continue
            value = getattr(node, f.name)
            result.extend(self.serialize(value))

        return bytes(result)
    
    def _serialize_type(self, t: Type) -> bytes:
        """Serialize a Type object."""
        result = bytearray([self.NODE_TAGS['Type']])
        
        # Serialize kind as string
        result.extend(self.serializer.encode_string(t.kind))
        
        # Serialize args
        result.extend(self.serializer.encode_leb128(len(t.args)))
        for arg in t.args:
            result.extend(self.serialize(arg))
        
        # Serialize optional name
        if t.name is not None:
            result.extend(b'\x01')  # has name
            result.extend(self.serializer.encode_string(t.name))
        else:
            result.extend(b'\x00')  # no name
        
        # Serialize optional mod5_bucket
        if t.mod5_bucket is not None:
            result.extend(b'\x01')  # has bucket
            result.extend(self.serializer.encode_leb128(t.mod5_bucket.value))
        else:
            result.extend(b'\x00')  # no bucket
        
        # Serialize optional structural_checksum
        if t.structural_checksum is not None:
            result.extend(b'\x01')  # has checksum
            for val in t.structural_checksum:
                result.extend(self.serializer.encode_leb128(val))
        else:
            result.extend(b'\x00')  # no checksum
        
        return bytes(result)
    
    def _serialize_type_var(self, tv: TypeVar) -> bytes:
        """Serialize a TypeVar object."""
        result = bytearray([self.NODE_TAGS['TypeVar']])
        
        # Serialize name (use empty string if None)
        name = tv.name if tv.name is not None else ''
        result.extend(self.serializer.encode_string(name))
        
        # Serialize id
        result.extend(self.serializer.encode_leb128(tv.id))
        
        return bytes(result)

    def _serialize_list(self, lst: List) -> bytes:
        result = bytearray()
        # Encode length
        result.extend(self.serializer.encode_leb128(len(lst)))
        for item in lst:
            result.extend(self.serialize(item))
        return bytes(result)

    def _serialize_primitive(self, value: Any) -> bytes:
        if value is None:
            return b'\x00'
        elif isinstance(value, bool):
            return b'\x01' if value else b'\x02'
        elif isinstance(value, int):
            # Check if it's a literal type tag
            if value in self.LITERAL_TAGS.values():
                return bytes([value])
            return self.serializer.encode_leb128(value)
        elif isinstance(value, float):
            # Encode as 8-byte IEEE 754
            import struct
            return b'\x03' + struct.pack('>d', value)
        elif isinstance(value, str):
            return self.serializer.encode_string(value)
        elif isinstance(value, dict):
            # Serialize dict as key-value pairs
            result = bytearray()
            result.extend(self.serializer.encode_leb128(len(value)))
            for k, v in sorted(value.items()):
                result.extend(self.serializer.encode_string(str(k)))
                result.extend(self.serialize(v))
            return bytes(result)
        elif isinstance(value, Enum):
            # Enum value could be string or int
            val = value.value
            if isinstance(val, str):
                return self.serializer.encode_string(val)
            else:
                return self.serializer.encode_leb128(val)
        else:
            raise ValueError(f"Cannot serialize primitive: {type(value)}")


class ASTBinaryDeserializer:
    """Deserialize AST nodes from custom binary format."""

    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0
        self.serializer = BinarySerializer()

    def deserialize(self) -> Any:
        if self.offset >= len(self.data):
            return None
        tag = self.data[self.offset]
        self.offset += 1
        if tag == 0:
            return None
        return self._deserialize_node(tag)

    def _deserialize_node(self, tag: int) -> Any:
        node_type_name = ASTBinarySerializer.TAG_TO_NODE.get(tag)
        if node_type_name is None:
            raise ValueError(f"Unknown node tag: {tag:#02x}")

        # This would need a full deserialization implementation
        # For now, return the raw data
        return {'_type': node_type_name, '_tag': tag}

    def _deserialize_primitive(self) -> Any:
        if self.offset >= len(self.data):
            raise ValueError("Unexpected end of data")
        tag = self.data[self.offset]
        self.offset += 1

        if tag == 0x00:
            return None
        elif tag in (0x01, 0x02):  # bool
            return tag == 0x01
        elif tag in self.LITERAL_TAGS.values():
            # Literal value follows
            return self._deserialize_primitive()
        elif tag == 0x03:  # float64
            import struct
            if self.offset + 8 > len(self.data):
                raise ValueError("Incomplete float64")
            val = struct.unpack('>d', self.data[self.offset:self.offset+8])[0]
            self.offset += 8
            return val
        else:
            # LEB128 integer
            self.offset -= 1  # Re-read the tag as part of LEB128
            return self.serializer.decode_leb128(self.data, self.offset)


def to_binary(ast: Any) -> bytes:
    """Serialize AST to custom binary format."""
    serializer = ASTBinarySerializer()
    return serializer.serialize(ast)


# Source-position fields on ASTNode.  They record WHERE a construct appeared, not WHAT it is,
# so they must not participate in a program identity.
POSITION_FIELDS = frozenset({'line', 'column', 'offset'})


def to_canonical_binary(ast: Any) -> bytes:
    """Serialize the AST into a position-independent *program identity* form.

    Why this exists: `to_binary` writes every dataclass field, including `line`, `column` and
    `offset`.  Two sources for the same program that differ only in indentation or comments
    therefore produced DIFFERENT hashes and DIFFERENT 231-gate triples (measured: the same
    function reformatted gave gate [38,170,0] vs [210,108,0]), and the Hebrew and ASCII
    spellings of the same keywords differed too.  That made the "deterministic AST
    fingerprint" a layout hash, useless as a reproducible-build cache key.

    This form omits the position fields, so it is a function of the program alone.  It is
    ONE-WAY: `ASTBinaryDeserializer._deserialize_node` is a stub that returns a dict, so no
    binary form can currently be read back (`from_binary(to_binary(ast)) != ast`, measured).
    Use this form for hashing and cache keys only.
    """
    return ASTBinarySerializer(canonical=True).serialize(ast)


def from_binary(data: bytes) -> Any:
    """Deserialize AST from custom binary format."""
    deserializer = ASTBinaryDeserializer(data)
    return deserializer.deserialize()


# ===== Round-trip Test =====

def test_roundtrip():
    """Test serialization round-trip."""
    from svl.parser_rd import parse
    from svl.lexer import tokenize

    test_code = '''
    module main {
      func main() type void {
        let x: int = 42
        if x > 0 then { return } else { return }
      }
    }
    '''

    tokens = tokenize(test_code)
    ast = parse(tokens)

    # Test JSON
    json_str = to_json(ast)
    ast_json = from_json(json_str)
    assert json.loads(json_str) == json.loads(to_json(ast_json))
    print("✓ JSON roundtrip OK")

    # Test msgpack
    mp_data = to_msgpack(ast)
    ast_mp = from_msgpack(mp_data)
    assert msgpack.unpackb(mp_data, raw=False) == msgpack.unpackb(to_msgpack(ast_mp), raw=False)
    print("✓ msgpack roundtrip OK")

    # Test binary (partial)
    bin_data = to_binary(ast)
    print(f"✓ Binary serialization: {len(bin_data)} bytes")
    print(f"  JSON size: {len(json_str)} bytes")
    print(f"  msgpack size: {len(mp_data)} bytes")
    print(f"  binary size: {len(bin_data)} bytes")


if __name__ == '__main__':
    test_roundtrip()