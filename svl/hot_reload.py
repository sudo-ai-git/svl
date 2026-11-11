# svl/hot_reload.py
# Hot Reloading with State Migration (H32)
# Runtime support for live code updates with automatic state migration

from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
import copy
import json
import hashlib
from pathlib import Path


class MigrationStrategy(Enum):
    """Strategy for migrating state during hot reload."""
    COMPATIBLE = "compatible"      # Only reload if types are compatible
    TRANSFORM = "transform"        # Apply transformation functions
    RESET = "reset"                # Reset state to defaults
    MANUAL = "manual"              # User provides migration logic


@dataclass
class TypeSchema:
    """Schema for a type (struct, enum, etc.) for version comparison."""
    name: str
    version: int
    fields: Dict[str, str]  # field_name -> type_name
    field_order: List[str]  # Preserve field order for layout compatibility
    
    def is_compatible_with(self, other: 'TypeSchema') -> bool:
        """Check if this schema is compatible with another (for hot reload)."""
        # Same name and version
        if self.name != other.name:
            return False
        
        # Check if all old fields exist in new with same type
        for field_name, field_type in self.fields.items():
            if field_name not in other.fields:
                return False  # Field removed
            if other.fields[field_name] != field_type:
                return False  # Field type changed
        
        # New fields are OK (will be initialized to defaults)
        return True
    
    def get_migration_plan(self, other: 'TypeSchema') -> 'MigrationPlan':
        """Generate migration plan from this schema to another."""
        plan = MigrationPlan(from_version=self.version, to_version=other.version)
        
        # Fields to keep (same name and type)
        for field_name in self.field_order:
            if field_name in other.fields and other.fields[field_name] == self.fields[field_name]:
                plan.keep_fields.append(field_name)
            elif field_name in other.fields:
                # Type changed - need transformation
                plan.transform_fields[field_name] = FieldTransform(
                    from_type=self.fields[field_name],
                    to_type=other.fields[field_name],
                    transform=None  # User must provide
                )
            else:
                # Field removed
                plan.remove_fields.append(field_name)
        
        # New fields to add
        for field_name in other.field_order:
            if field_name not in self.fields:
                plan.add_fields.append(FieldAddition(
                    name=field_name,
                    type_name=other.fields[field_name],
                    default=None  # User must provide
                ))
        
        return plan


@dataclass
class FieldTransform:
    """Transformation for a field with changed type."""
    from_type: str
    to_type: str
    transform: Optional[Callable[[Any], Any]]  # from_value -> to_value


@dataclass
class FieldAddition:
    """New field to add with default value."""
    name: str
    type_name: str
    default: Any


@dataclass
class MigrationPlan:
    """Plan for migrating state between schema versions."""
    from_version: int
    to_version: int
    keep_fields: List[str] = field(default_factory=list)
    transform_fields: Dict[str, FieldTransform] = field(default_factory=dict)
    remove_fields: List[str] = field(default_factory=list)
    add_fields: List[FieldAddition] = field(default_factory=list)
    
    def is_trivial(self) -> bool:
        """Check if migration is trivial (no transformations needed).
        
        Adding fields with defaults is considered trivial since it doesn't
        require data transformation.
        """
        return (not self.transform_fields and 
                not self.remove_fields)


class StateMigrator:
    """Migrates runtime state between schema versions."""
    
    def __init__(self):
        self.schemas: Dict[str, Dict[int, TypeSchema]] = {}  # type_name -> version -> schema
        self.transformers: Dict[str, Callable] = {}  # Custom transformers
    
    def register_schema(self, schema: TypeSchema):
        """Register a type schema."""
        if schema.name not in self.schemas:
            self.schemas[schema.name] = {}
        self.schemas[schema.name][schema.version] = schema
    
    def get_schema(self, type_name: str, version: int) -> Optional[TypeSchema]:
        """Get schema for a specific version."""
        return self.schemas.get(type_name, {}).get(version)
    
    def get_latest_schema(self, type_name: str) -> Optional[TypeSchema]:
        """Get latest version of schema."""
        versions = self.schemas.get(type_name, {})
        if not versions:
            return None
        latest_version = max(versions.keys())
        return versions[latest_version]
    
    def register_transformer(self, type_name: str, transformer: Callable):
        """Register custom transformer for a type."""
        self.transformers[type_name] = transformer
    
    def migrate(self, state: Dict[str, Any], type_name: str, 
                from_version: int, to_version: int) -> Dict[str, Any]:
        """Migrate state for a type from one version to another."""
        if type_name not in self.schemas:
            raise ValueError(f"Unknown type: {type_name}")
        
        # Get the schema for the from_version
        old_schema = self.get_schema(type_name, from_version)
        if not old_schema:
            raise ValueError(f"No schema for {type_name} version {from_version}")
        
        # If already at target version, no migration needed
        if from_version == to_version:
            return state
        
        # Get target schema
        new_schema = self.get_schema(type_name, to_version)
        if not new_schema:
            raise ValueError(f"No schema for {type_name} version {to_version}")
        
        # Check compatibility
        if old_schema.is_compatible_with(new_schema):
            # Trivial migration - just copy compatible fields
            return self._migrate_compatible(state, old_schema, new_schema)
        
        # Generate migration plan
        plan = old_schema.get_migration_plan(new_schema)
        
        # Check if we have all required transformers
        for field_name, transform in plan.transform_fields.items():
            if transform.transform is None and field_name not in self.transformers:
                raise ValueError(f"No transformer for field {field_name} ({transform.from_type} -> {transform.to_type})")
        
        # Apply migration plan
        return self._apply_migration_plan(state, plan)
    
    def _migrate_compatible(self, state: Dict[str, Any], 
                           old_schema: TypeSchema, new_schema: TypeSchema) -> Dict[str, Any]:
        """Migrate state with compatible schemas."""
        new_state = {}
        
        # Keep compatible fields
        for field_name in old_schema.field_order:
            if field_name in new_schema.fields:
                new_state[field_name] = state.get(field_name)
        
        # Add new fields with defaults
        for field_name in new_schema.field_order:
            if field_name not in old_schema.fields:
                # Try to get default from schema or use type default
                new_state[field_name] = self._get_default_value(new_schema.fields[field_name])
        
        return new_state
    
    def _apply_migration_plan(self, state: Dict[str, Any], plan: MigrationPlan) -> Dict[str, Any]:
        """Apply migration plan to state."""
        new_state = {}
        
        # Keep fields
        for field_name in plan.keep_fields:
            new_state[field_name] = state.get(field_name)
        
        # Transform fields
        for field_name, transform in plan.transform_fields.items():
            old_value = state.get(field_name)
            if transform.transform:
                new_state[field_name] = transform.transform(old_value)
            elif field_name in self.transformers:
                new_state[field_name] = self.transformers[field_name](old_value)
            else:
                new_state[field_name] = old_value
        
        # Add new fields
        for addition in plan.add_fields:
            new_state[addition.name] = addition.default if addition.default is not None else \
                self._get_default_value(addition.type_name)
        
        # Note: removed fields are simply not copied
        
        return new_state
    
    def _get_default_value(self, type_name: str) -> Any:
        """Get default value for a type."""
        defaults = {
            'int': 0,
            'float': 0.0,
            'bool': False,
            'string': '',
            'void': None,
        }
        return defaults.get(type_name, None)


@dataclass
class ModuleVersion:
    """Version info for a module."""
    name: str
    version: int
    checksum: str  # Source checksum
    exports: List[str]
    schemas: Dict[str, TypeSchema]


class HotReloadManager:
    """Manages hot reloading of modules with state migration."""
    
    def __init__(self):
        self.modules: Dict[str, ModuleVersion] = {}  # name -> version
        self.module_states: Dict[str, Dict[str, Any]] = {}  # module_name -> state
        self.migrator = StateMigrator()
        self.reload_callbacks: List[Callable] = []
    
    def register_module(self, module: ModuleVersion):
        """Register a module version."""
        self.modules[module.name] = module
        # Register schemas
        for schema in module.schemas.values():
            self.migrator.register_schema(schema)
    
    def get_module_state(self, module_name: str) -> Dict[str, Any]:
        """Get current state for a module."""
        return self.module_states.get(module_name, {})
    
    def set_module_state(self, module_name: str, state: Dict[str, Any]):
        """Set state for a module."""
        self.module_states[module_name] = state
    
    def can_reload(self, module_name: str, new_source: str) -> bool:
        """Check if module can be hot reloaded."""
        if module_name not in self.modules:
            return True  # First load
        
        old_module = self.modules[module_name]
        new_checksum = hashlib.sha256(new_source.encode()).hexdigest()
        
        if old_module.checksum == new_checksum:
            return False  # No changes
        
        # Check if exports are compatible
        # In real implementation, would parse new source and compare
        return True
    
    def reload_module(self, module_name: str, new_source: str, 
                     new_module: ModuleVersion) -> bool:
        """Hot reload a module with state migration."""
        if module_name not in self.modules:
            # First load
            self.register_module(new_module)
            return True
        
        old_module = self.modules[module_name]
        old_state = self.module_states.get(module_name, {})
        
        # Register new module's schemas with migrator BEFORE migration
        for schema in new_module.schemas.values():
            self.migrator.register_schema(schema)
        
        # Migrate state for each exported type
        new_state = {}
        for type_name, schema in new_module.schemas.items():
            if type_name in old_module.schemas:
                old_schema = old_module.schemas[type_name]
                if old_schema.is_compatible_with(schema):
                    # Compatible - migrate state
                    # Extract the state for this specific type
                    type_state = old_state.get(type_name, {})
                    new_state[type_name] = self.migrator.migrate(
                        type_state, type_name, old_schema.version, schema.version)
                else:
                    # Incompatible - reset or use custom migration
                    new_state[type_name] = {}
            else:
                # New type - initialize empty
                new_state[type_name] = {}
        
        # Update module registry
        self.modules[module_name] = new_module
        self.module_states[module_name] = new_state
        
        # Notify callbacks
        for callback in self.reload_callbacks:
            callback(module_name, old_module, new_module)
        
        return True
    
    def on_reload(self, callback: Callable):
        """Register callback for reload events."""
        self.reload_callbacks.append(callback)


class WASMHotReloadRuntime:
    """WASM runtime support for hot reloading."""
    
    def __init__(self, manager: HotReloadManager):
        self.manager = manager
        self.instance: Optional[Any] = None  # WASM instance
        self.memory: Optional[Any] = None
    
    def instantiate(self, wasm_binary: bytes, imports: Dict[str, Any]) -> Any:
        """Instantiate WASM module with hot reload support."""
        # Add hot reload imports
        imports['hot_reload'] = {
            'get_state': self._get_state,
            'set_state': self._set_state,
            'notify_reload': self._notify_reload,
        }
        
        # In real implementation, would use wasmtime or similar
        # self.instance = wasmtime.Instance(wasm_binary, imports)
        return self.instance
    
    def _get_state(self, module_name_ptr: int, module_name_len: int) -> int:
        """Get serialized state for a module."""
        # Read module name from memory
        # module_name = self.memory.read(module_name_ptr, module_name_len).decode()
        # state = self.manager.get_module_state(module_name)
        # Serialize and write to memory
        return 0  # Pointer to state in memory
    
    def _set_state(self, module_name_ptr: int, module_name_len: int, 
                   state_ptr: int, state_len: int) -> None:
        """Set state for a module."""
        pass
    
    def _notify_reload(self, module_name_ptr: int, module_name_len: int) -> None:
        """Notify runtime of reload."""
        pass


def create_hot_reload_wasm_imports() -> str:
    """Generate WASM imports for hot reload support."""
    return '''
;; Hot reload imports
(import "hot_reload" "get_state" (func $hr_get_state (param i32 i32) (result i32)))
(import "hot_reload" "set_state" (func $hr_set_state (param i32 i32 i32 i32)))
(import "hot_reload" "notify_reload" (func $hr_notify_reload (param i32 i32)))
'''


if __name__ == '__main__':
    # Test hot reload
    print("=== Hot Reload Test ===")
    
    # Create schemas
    point_v1 = TypeSchema(
        name="Point",
        version=1,
        fields={"x": "int", "y": "int"},
        field_order=["x", "y"]
    )
    
    point_v2 = TypeSchema(
        name="Point",
        version=2,
        fields={"x": "int", "y": "int", "z": "int"},
        field_order=["x", "y", "z"]
    )
    
    # Test compatibility
    print(f"Point v1 compatible with v2: {point_v1.is_compatible_with(point_v2)}")
    
    # Test migration plan
    plan = point_v1.get_migration_plan(point_v2)
    print(f"Migration plan: keep={plan.keep_fields}, add={[(a.name, a.type_name) for a in plan.add_fields]}")
    
    # Test state migrator
    migrator = StateMigrator()
    migrator.register_schema(point_v1)
    migrator.register_schema(point_v2)
    
    old_state = {"x": 10, "y": 20}
    new_state = migrator.migrate(old_state, "Point", 2)
    print(f"Migrated state: {new_state}")
    
    # Test hot reload manager
    manager = HotReloadManager()
    
    module_v1 = ModuleVersion(
        name="geometry",
        version=1,
        checksum="abc123",
        exports=["Point"],
        schemas={"Point": point_v1}
    )
    
    module_v2 = ModuleVersion(
        name="geometry",
        version=2,
        checksum="def456",
        exports=["Point"],
        schemas={"Point": point_v2}
    )
    
    manager.register_module(module_v1)
    manager.set_module_state("geometry", {"Point": {"x": 10, "y": 20}})
    
    print(f"State before reload: {manager.get_module_state('geometry')}")
    
    manager.reload_module("geometry", "new source", module_v2)
    print(f"State after reload: {manager.get_module_state('geometry')}")