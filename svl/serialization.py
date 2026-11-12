# svl/serialization.py
# AST Serialization for Spike S3
# JSON, msgpack, custom binary formats

import json
import msgpack
import struct
import typing
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


def _build_node_registry() -> Dict[str, type]:
    """Map node class name -> class, for every tag in NODE_TAGS."""
    import svl.parser_rd as pr
    registry: Dict[str, type] = {}
    for name in ASTBinarySerializer.NODE_TAGS:
        cls = getattr(pr, name, None)
        if cls is None and name == 'Type':
            cls = Type
        elif cls is None and name == 'TypeVar':
            cls = TypeVar
        if cls is not None:
            registry[name] = cls
    return registry


_NODE_REGISTRY = _build_node_registry()

_NONE_TYPE = type(None)


def _classify(hint: Any):
    """Normalise a type annotation into a (kind, inner) decoding descriptor.

    kind is one of: none, int, bool, str, float, enum, node, list, dict, optional, union,
    optional_union, any.
    """
    if hint is None or hint is Any:
        return ('any', None)
    if hint is _NONE_TYPE:
        return ('none', None)
    if hint is int:
        return ('int', None)
    if hint is bool:
        return ('bool', None)
    if hint is str:
        return ('str', None)
    if hint is float:
        return ('float', None)

    origin = typing.get_origin(hint)
    if origin in (list, List):
        args = typing.get_args(hint)
        return ('list', args[0] if args else Any)
    if origin in (dict, Dict):
        args = typing.get_args(hint)
        return ('dict', args[1] if len(args) > 1 else Any)
    if origin is Union:
        args = list(typing.get_args(hint))
        has_none = _NONE_TYPE in args
        rest = [a for a in args if a is not _NONE_TYPE]
        if len(rest) == 1:
            kind, inner = _classify(rest[0])
            return ('optional' if has_none else kind, inner)
        return ('optional_union' if has_none else 'union', rest)

    if isinstance(hint, type):
        if issubclass(hint, Enum):
            return ('enum', hint)
        if is_dataclass(hint):
            return ('node', hint)
    return ('any', None)


class ASTBinaryDeserializer:
    """Deserialize AST nodes from the custom binary format.

    **The format is not self-describing.**  The writer emits primitives with no type tag, so
    an int in 1..5, a bool and a string of length 1..5 all begin with the same byte.  The
    reader therefore uses the *declared field type* -- exactly the information the writer had
    -- to pick a decoding.  Three fields have unions too wide for that alone
    (`Literal.value`, `Pattern.value`, `TypeExpr.value`); each is disambiguated by a sibling
    discriminator the writer emitted earlier in the same node (`literal_type` / `kind`), and
    `Type.args` by `Type.kind`.

    `to_binary` is UNCHANGED and byte-identical, so nothing that hashes it (the 231-gate over
    a serialised AST, the golden references, the bootstrap) is affected.  The cost of that
    choice is that this reader cannot infer a bare primitive with no type context: it raises
    instead of guessing.
    """

    #: field -> sibling discriminator that selects the decoding, for unions too wide to read
    _DISCRIMINATED = {
        ('Literal', 'value'): 'literal_type',
        ('Pattern', 'value'): 'kind',
        ('TypeExpr', 'value'): 'kind',
    }

    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0
        self.serializer = BinarySerializer()

    # ---- primitives -------------------------------------------------------

    def _read_byte(self) -> int:
        if self.offset >= len(self.data):
            raise ValueError("Unexpected end of data")
        b = self.data[self.offset]
        self.offset += 1
        return b

    def _read_raw(self, n: int) -> bytes:
        if self.offset + n > len(self.data):
            raise ValueError("Unexpected end of data")
        b = self.data[self.offset:self.offset + n]
        self.offset += n
        return b

    def _read_leb(self) -> int:
        val, self.offset = self.serializer.decode_leb128(self.data, self.offset)
        return val

    def _read_string(self) -> str:
        s, self.offset = self.serializer.decode_string(self.data, self.offset)
        return s

    # ---- entry point ------------------------------------------------------

    def deserialize(self) -> Any:
        if self.offset >= len(self.data):
            return None
        return self._read_value(None)

    # ---- typed reading ----------------------------------------------------

    def _read_value(self, hint: Any) -> Any:
        kind, inner = _classify(hint)

        if kind == 'none':
            return None
        if kind == 'int':
            return self._read_leb()
        if kind == 'bool':
            b = self._read_byte()
            if b == 0x01:
                return True
            if b == 0x02:
                return False
            raise ValueError(f"Bad bool tag {b:#04x} at offset {self.offset - 1}")
        if kind == 'str':
            return self._read_string()
        if kind == 'float':
            if self._read_byte() != 0x03:
                raise ValueError("Expected a float tag (0x03)")
            return struct.unpack('>d', self._read_raw(8))[0]
        if kind == 'enum':
            sample = next(iter(inner))
            if isinstance(sample.value, str):
                return inner(self._read_string())
            return inner(self._read_leb())
        if kind == 'node':
            return self._read_node(inner)
        if kind == 'list':
            n = self._read_leb()
            return [self._read_value(inner) for _ in range(n)]
        if kind == 'dict':
            n = self._read_leb()
            return {self._read_string(): self._read_value(inner) for _ in range(n)}
        if kind == 'optional':
            if self.data[self.offset] == 0x00:
                self.offset += 1
                return None
            return self._read_value(inner)
        if kind in ('union', 'optional_union'):
            if kind == 'optional_union' and self.data[self.offset] == 0x00:
                self.offset += 1
                return None
            return self._read_node_tagged()
        if kind == 'any':
            return self._read_node_tagged()
        raise ValueError(f"Unsupported type hint {hint!r}")

    def _read_node_tagged(self) -> Any:
        """Read a tag byte and dispatch. Used where the writer's type is a node union."""
        tag = self._read_byte()
        name = ASTBinarySerializer.TAG_TO_NODE.get(tag)
        if name is None:
            raise ValueError(
                f"Unknown node tag {tag:#04x} at offset {self.offset - 1}; the binary format "
                f"is not self-describing, so a bare primitive cannot be read without a type hint")
        return self._read_node_body(name)

    def _read_node(self, cls) -> Any:
        tag = self._read_byte()
        name = ASTBinarySerializer.TAG_TO_NODE.get(tag)
        if name is None:
            raise ValueError(f"Unknown node tag {tag:#04x} at offset {self.offset - 1}")
        if name != cls.__name__:
            # The declared hint and the actual tag disagree; trust the tag (it is what was
            # written) but keep going rather than silently building the wrong node.
            return self._read_node_body(name)
        return self._read_node_body(name)

    def _read_node_body(self, name: str) -> Any:
        if name == 'Type':
            return self._read_type_body()
        if name == 'TypeVar':
            return self._read_type_var_body()

        cls = _NODE_REGISTRY.get(name)
        if cls is None:
            raise ValueError(f"Unknown node type {name!r}")
        try:
            hints = typing.get_type_hints(cls)
        except Exception:                                            # noqa: BLE001
            hints = {}

        values: Dict[str, Any] = {}
        # The writer serialises fields sorted by name -- the same order used here.
        for f in sorted(fields(cls), key=lambda x: x.name):
            hint = hints.get(f.name, f.type)
            discriminator = self._DISCRIMINATED.get((name, f.name))
            if discriminator is not None:
                values[f.name] = self._read_discriminated(name, f.name,
                                                          values[discriminator])
            else:
                values[f.name] = self._read_value(hint)
        return cls(**values)

    def _read_discriminated(self, node_name: str, field_name: str, discriminator: str) -> Any:
        """Decode a field whose declared union is too wide, using a sibling value."""
        if node_name == 'Literal':
            return {
                'int': self._read_leb,
                'bool': self._read_value_bool,
                'float': self._read_float,
                'string': self._read_string,
                'null': self._read_none,
            }.get(discriminator, self._read_node_tagged)()
        if node_name == 'Pattern':
            # The parser uses the LITERAL TYPE as the pattern kind ('int', 'float', 'string',
            # 'bool', 'null'), plus 'wildcard', 'ident' and 'struct'.
            return {
                'int': self._read_leb,
                'float': self._read_float,
                'string': self._read_string,
                'bool': self._read_value_bool,
                'null': self._read_none,
                'wildcard': self._read_none,
                'ident': self._read_string,
                'struct': self._read_field_patterns,
            }.get(discriminator, self._read_node_tagged)()
        if node_name == 'TypeExpr':
            if discriminator in ('prim', 'struct'):
                return self._read_string()
            if discriminator == 'array':
                return self._read_node_tagged()
            if discriminator == 'tuple':
                n = self._read_leb()
                return [self._read_node_tagged() for _ in range(n)]
            if discriminator == 'func':
                return self._read_node_tagged()
            if discriminator == 'generic':
                # dict {name: str, args: [TypeExpr]} -- the writer sorts keys, so 'args'
                # precedes 'name' on the wire.
                n = self._read_leb()
                out = {}
                for _ in range(n):
                    k = self._read_string()
                    if k == 'args':
                        m = self._read_leb()
                        out[k] = [self._read_node_tagged() for _ in range(m)]
                    else:
                        out[k] = self._read_string()
                return out
            return self._read_node_tagged()
        return self._read_node_tagged()

    def _read_value_bool(self) -> bool:
        return self._read_value(bool)

    def _read_float(self) -> float:
        return self._read_value(float)

    def _read_field_patterns(self) -> List[Any]:
        n = self._read_leb()
        return [self._read_node_tagged() for _ in range(n)]

    def _read_none(self) -> None:
        """Consume the writer's null marker.  A field whose value is None is still WRITTEN
        (as 0x00), so it must be consumed even when the kind already implies None."""
        b = self._read_byte()
        if b != 0x00:
            raise ValueError(f"Expected a null marker (0x00), got {b:#04x} "
                             f"at offset {self.offset - 1}")

    # ---- Type / TypeVar (custom wire formats) -----------------------------

    def _read_type_body(self) -> Any:
        from svl.mod5_types import Mod5Bucket
        kind = self._read_string()
        n = self._read_leb()
        args = []
        for _ in range(n):
            # args are Type | TypeVar | str, discriminated by the leading tag.
            b = self.data[self.offset]
            if b == ASTBinarySerializer.NODE_TAGS['Type']:
                self._read_byte()
                args.append(self._read_type_body())
            elif b == ASTBinarySerializer.NODE_TAGS['TypeVar']:
                self._read_byte()
                args.append(self._read_type_var_body())
            else:
                args.append(self._read_string())

        name = None
        if self._read_byte() == 0x01:
            name = self._read_string()
        mod5_bucket = None
        if self._read_byte() == 0x01:
            mod5_bucket = Mod5Bucket(self._read_leb())
        structural_checksum = None
        if self._read_byte() == 0x01:
            structural_checksum = (self._read_leb(), self._read_leb(), self._read_leb())

        # Type.__init__ takes **kwargs and deliberately ignores `name`, so it must be
        # assigned after construction -- passing it to the constructor silently drops it.
        t = Type(kind, args=args)
        t.name = name
        t.mod5_bucket = mod5_bucket
        t.structural_checksum = structural_checksum
        return t

    def _read_type_var_body(self) -> Any:
        name = self._read_string()
        tid = self._read_leb()
        tv = TypeVar(name)
        tv.id = tid          # the wire carries the original id; the constructor minted a new one
        return tv


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
    ONE-WAY BY DESIGN: `from_binary` reads the positional form `to_binary` writes, and
    reconstructing nodes from a canonical stream would require the omitted fields.  Use it
    for hashing and cache keys only.
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

    # Test binary round-trip
    bin_data = to_binary(ast)
    ast_back = from_binary(bin_data)
    assert ast_to_dict(ast_back) == ast_to_dict(ast), "binary round-trip is not structurally equal"
    assert to_binary(ast_back) == bin_data, "binary round-trip is not byte-stable"
    print(f"✓ Binary roundtrip OK ({len(bin_data)} bytes)")
    print(f"  JSON size: {len(json_str)} bytes")
    print(f"  msgpack size: {len(mp_data)} bytes")
    print(f"  binary size: {len(bin_data)} bytes")


if __name__ == '__main__':
    test_roundtrip()