"""Conservative mark-sweep collector for SVL's linear-memory heap.

SVL has no WASM stack maps, so a *precise moving* collector is impossible here: values
held only in WASM locals or on the operand stack cannot be enumerated by generated code.
This collector therefore makes deliberate, documented choices:

1. **Non-moving (mark-sweep).** Object addresses never change, so a stale handle stays
   readable.  What the collector guarantees is that every object reachable from a
   recorded ROOT is still allocated afterwards.
2. **Conservative tracing.** Every word inside a live block is treated as a potential
   pointer.  A candidate is followed only when it lands on a REAL block start, answered
   by an out-of-band bitmap.  This can retain garbage — an integer equal to a real block
   address keeps that block alive — but it can neither free something live nor write
   outside a genuine block header.

ROOTS are recorded by the compiler:

* word-sized module globals, and
* word-sized parameters and locals, pushed onto a shadow stack at function entry and
  again after every assignment to such a name.  A frame's entries are dropped when the
  function returns (the frame's entry offset is saved in a local).

MEMORY LAYOUT (fixed absolute addresses, reserved by the compiler for any program that
calls ``gc()``)::

    [0, heap_base)              static string data
    [heap_base, BITMAP_BASE)    the heap; blocks are 8-byte aligned
    [BITMAP_BASE, +128 KiB)     1 bit per 8-byte slot: "this slot starts a block"
    [MARK_BASE,   +32 KiB)      explicit mark stack used while tracing
    [SHADOW_BASE, +32 KiB)      root shadow stack, one word per recorded root

Because the regions sit at fixed addresses there is nothing to relocate when
``memory.grow`` succeeds; the heap simply grows up to ``BITMAP_BASE``.  A heap needing
more than that is an honest out-of-memory trap, not silent corruption.

The collector runs only when the program calls ``gc()``.  That is a deliberate safepoint
restriction: a heap pointer held only in a temporary (on the WASM operand stack) cannot
be a root, so implicit collection during expression evaluation would be unsound.  Call
``gc()`` at a statement boundary, not while an unassigned heap pointer is live in a
temporary.
"""
from typing import List

# Block header layout: one i32 immediately before the payload.
#   bits 0..29  total block size, including the 4-byte header
#   bit  30     FREE — the block is on the free list
#   bit  31     MARK — reachable in this collection
HEADER_SIZE = 4
SIZE_MASK = 0x3FFFFFFF
FREE_BIT = 0x40000000
MARK_BIT = 0x80000000

# Blocks are padded to this boundary, so every block start is 8-byte aligned.
BLOCK_ALIGN = 8

# Reserved region sizes and their fixed addresses.
HEAP_CAPACITY = 8 * 1024 * 1024          # the heap may grow up to BITMAP_BASE
BITMAP_BYTES = HEAP_CAPACITY // 64       # 1 bit per 8-byte slot over the heap
MARKSTACK_SLOTS = 8192
MARKSTACK_BYTES = MARKSTACK_SLOTS * 4
SHADOW_SLOTS = 8192
SHADOW_BYTES = SHADOW_SLOTS * 4

BITMAP_BASE = HEAP_CAPACITY
MARK_BASE = BITMAP_BASE + BITMAP_BYTES
SHADOW_BASE = MARK_BASE + MARKSTACK_BYTES
REQUIRED_BYTES = SHADOW_BASE + SHADOW_BYTES


def globals_lines() -> List[str]:
    return [
        '  (global $shadow_off (mut i32) (i32.const 0))',
        '  (global $ms_sp (mut i32) (i32.const 0))',
    ]


def set_block_bit_lines(heap_base: int) -> List[str]:
    """Set the "this slot starts a block" bit for the block whose header is in ``$p``.

    Emitted inside ``$alloc`` right after the header is stored.  Uses ``$sb``/``$nb``
    as scratch; both are dead at that point.
    """
    return [
        '    local.get $p',
        f'    i32.const {heap_base}',
        '    i32.sub',
        '    i32.const 3',
        '    i32.shr_u',
        '    local.set $nb',
        '    local.get $nb',
        '    i32.const 3',
        '    i32.shr_u',
        f'    i32.const {BITMAP_BASE}',
        '    i32.add',
        '    local.set $sb',
        # `i32.store8` wants [address, value]: push the address FIRST, then build the
        # new byte value on top of it.
        '    local.get $sb',
        '    local.get $sb',
        '    i32.load8_u',
        '    i32.const 1',
        '    local.get $nb',
        '    i32.const 7',
        '    i32.and',
        '    i32.shl',
        '    i32.or',
        '    i32.store8',
    ]


def _candidate_bit_test_lines(heap_base: int) -> List[str]:
    """Test whether the address in ``$b`` is a registered block start.

    Leaves a non-zero i32 when it is.  Uses ``$slot`` as scratch.
    """
    return [
        '    local.get $b',
        f'    i32.const {heap_base}',
        '    i32.sub',
        '    i32.const 3',
        '    i32.shr_u',
        '    local.set $slot',
        '    local.get $slot',
        '    i32.const 3',
        '    i32.shr_u',
        f'    i32.const {BITMAP_BASE}',
        '    i32.add',
        '    i32.load8_u',
        '    i32.const 1',
        '    local.get $slot',
        '    i32.const 7',
        '    i32.and',
        '    i32.shl',
        '    i32.and',
    ]


def mark_value_lines(heap_base: int) -> List[str]:
    """``$mark_value(v)``: mark the block ``v`` refers to, if any, and queue its fields."""
    L: List[str] = ['  (func $mark_value (param $v i32)',
                    '    (local $b i32) (local $size i32) (local $slot i32)']
    L += [
        # --- the candidate block address must lie inside the heap -----------
        '    local.get $v',
        f'    i32.const {HEADER_SIZE}',
        '    i32.sub',
        f'    i32.const {heap_base}',
        '    i32.lt_u',
        '    if',
        '      return',
        '    end',
        '    local.get $v',
        f'    i32.const {HEADER_SIZE}',
        '    i32.sub',
        '    global.get $heap',
        '    i32.ge_u',
        '    if',
        '      return',
        '    end',
        '    local.get $v',
        f'    i32.const {HEADER_SIZE}',
        '    i32.sub',
        '    local.set $b',
        # --- a real block start is 8-byte aligned (see BLOCK_ALIGN) -----------
        # Without this, an interior word four bytes into a block (the array length,
        # say) maps to the same bitmap slot as the block itself and is mistaken for
        # its header — which then gets a MARK bit written over user data.
        '    local.get $b',
        f'    i32.const {BLOCK_ALIGN - 1}',
        '    i32.and',
        '    if',
        '      return',
        '    end',
        # --- it must be a registered block start (out-of-band bitmap) --------
        *_candidate_bit_test_lines(heap_base),
        '    i32.eqz',
        '    if',
        '      return',
        '    end',
        # --- its header must describe a whole block ending before $heap -----
        '    local.get $b',
        '    i32.load',
        f'    i32.const {SIZE_MASK}',
        '    i32.and',
        '    local.set $size',
        '    local.get $size',
        f'    i32.const {HEADER_SIZE}',
        '    i32.lt_u',
        '    if',
        '      return',
        '    end',
        '    local.get $b',
        '    local.get $size',
        '    i32.add',
        '    global.get $heap',
        '    i32.gt_u',
        '    if',
        '      return',
        '    end',
        # --- already marked, or already on the free list: nothing to do ----
        '    local.get $b',
        '    i32.load',
        f'    i32.const {MARK_BIT | FREE_BIT}',
        '    i32.and',
        '    i32.eqz',
        '    if',
        # set MARK
        '      local.get $b',
        '      local.get $b',
        '      i32.load',
        f'      i32.const {MARK_BIT}',
        '      i32.or',
        '      i32.store',
        # push $b at MARK_BASE + $ms_sp, bounds-checked
        '      global.get $ms_sp',
        f'      i32.const {MARKSTACK_BYTES}',
        '      i32.ge_u',
        '      if',
        '        unreachable',
        '      end',
        f'      i32.const {MARK_BASE}',
        '      global.get $ms_sp',
        '      i32.add',
        '      local.get $b',
        '      i32.store',
        '      global.get $ms_sp',
        '      i32.const 4',
        '      i32.add',
        '      global.set $ms_sp',
        '    end',
        '  )',
    ]
    return L


def gc_lines(heap_base: int, pointer_globals: List[str]) -> List[str]:
    """``$gc``: mark from the roots, then sweep the heap.

    Sweep walks blocks contiguously from the heap base following each header's size, so
    it terminates exactly at the bump pointer.  Unmarked blocks are pushed onto the
    free list; blocks already carrying FREE keep their existing list links.
    """
    L: List[str] = ['  (func $gc',
                    '    (local $p i32) (local $hdr i32) (local $size i32)',
                    '    (local $w i32) (local $end i32)',
                    '    i32.const 0',
                    '    global.set $ms_sp']

    # ---- roots: the shadow stack ---------------------------------------------
    L += [
        '    i32.const 0',
        '    local.set $w',
        '    block $roots_done',
        '      loop $roots',
        '        local.get $w',
        '        global.get $shadow_off',
        '        i32.ge_u',
        '        br_if $roots_done',
        f'        i32.const {SHADOW_BASE}',
        '        local.get $w',
        '        i32.add',
        '        i32.load',
        '        call $mark_value',
        '        local.get $w',
        '        i32.const 4',
        '        i32.add',
        '        local.set $w',
        '        br $roots',
        '      end',
        '    end',
    ]

    # ---- roots: word-sized module globals ------------------------------------
    for name in pointer_globals:
        L += [f'    global.get ${name}', '    call $mark_value']

    # ---- trace ---------------------------------------------------------------
    L += [
        '    block $trace_done',
        '      loop $trace',
        '        global.get $ms_sp',
        '        i32.eqz',
        '        br_if $trace_done',
        '        global.get $ms_sp',
        '        i32.const 4',
        '        i32.sub',
        '        global.set $ms_sp',
        f'        i32.const {MARK_BASE}',
        '        global.get $ms_sp',
        '        i32.add',
        '        i32.load',
        '        local.set $p',
        '        local.get $p',
        '        i32.load',
        f'        i32.const {SIZE_MASK}',
        '        i32.and',
        '        local.set $size',
        '        local.get $p',
        f'        i32.const {HEADER_SIZE}',
        '        i32.add',
        '        local.set $w',
        '        local.get $p',
        '        local.get $size',
        '        i32.add',
        '        local.set $end',
        '        block $scan_done',
        '          loop $scan',
        '            local.get $w',
        '            local.get $end',
        '            i32.ge_u',
        '            br_if $scan_done',
        '            local.get $w',
        '            i32.load',
        '            call $mark_value',
        '            local.get $w',
        '            i32.const 4',
        '            i32.add',
        '            local.set $w',
        '            br $scan',
        '          end',
        '        end',
        '        br $trace',
        '      end',
        '    end',
    ]

    # ---- sweep ---------------------------------------------------------------
    L += [
        f'    i32.const {heap_base}',
        '    local.set $p',
        '    block $sweep_done',
        '      loop $sweep',
        '        local.get $p',
        '        global.get $heap',
        '        i32.ge_u',
        '        br_if $sweep_done',
        '        local.get $p',
        '        i32.load',
        '        local.set $hdr',
        '        local.get $hdr',
        f'        i32.const {SIZE_MASK}',
        '        i32.and',
        '        local.set $size',
        # a zero size means the heap is not where we think it is: stop, do not spin
        '        local.get $size',
        '        i32.eqz',
        '        br_if $sweep_done',
        '        local.get $hdr',
        f'        i32.const {MARK_BIT}',
        '        i32.and',
        '        if',
        # reachable: clear the mark bit
        '          local.get $p',
        '          local.get $hdr',
        f'          i32.const {MARK_BIT}',
        '          i32.xor',
        '          i32.store',
        '        else',
        '          local.get $hdr',
        f'          i32.const {FREE_BIT}',
        '          i32.and',
        '          i32.eqz',
        '          if',
        # unmarked and not already free: push onto the free list
        '            local.get $p',
        '            local.get $hdr',
        f'            i32.const {FREE_BIT}',
        '            i32.or',
        '            i32.store',
        '            local.get $p',
        '            i32.const 4',
        '            i32.add',
        '            global.get $free_list',
        '            i32.store',
        '            local.get $p',
        '            global.set $free_list',
        '          end',
        '        end',
        '        local.get $p',
        '        local.get $size',
        '        i32.add',
        '        local.set $p',
        '        br $sweep',
        '      end',
        '    end',
        '  )',
    ]
    return L


def alloc_free_hit_lines() -> List[str]:
    """Clear the FREE bit on a block taken from the free list, before returning it."""
    return [
        '        local.get $cur',
        '        i32.const 4',
        '        i32.sub',
        '        local.get $cur',
        '        i32.const 4',
        '        i32.sub',
        '        i32.load',
        f'        i32.const {FREE_BIT}',
        '        i32.xor',
        '        i32.store',
    ]


def free_lines() -> List[str]:
    """`$free`: mark the block FREE (idempotent) and push it onto the free list."""
    return [
        '    local.get $payload',
        '    i32.const 4',
        '    i32.sub',
        '    local.set $b',
        # double-free would put one block twice on the list; refuse it instead
        '    local.get $b',
        '    i32.load',
        f'    i32.const {FREE_BIT}',
        '    i32.and',
        '    if',
        '      return',
        '    end',
        '    local.get $b',
        '    local.get $b',
        '    i32.load',
        f'    i32.const {FREE_BIT}',
        '    i32.or',
        '    i32.store',
        '    local.get $b',
        '    i32.const 4',
        '    i32.add',
        '    global.get $free_list',
        '    i32.store',
        '    local.get $b',
        '    global.set $free_list',
    ]


def heap_reset_extra_lines() -> List[str]:
    """`$heap_reset` also drops every recorded root: the heap it referred to is gone."""
    return [
        '    i32.const 0',
        '    global.set $shadow_off',
    ]


def shadow_push_lines(name: str) -> List[str]:
    """Record one more root: store `local $name` at the shadow stack top."""
    return (
        ['global.get $shadow_off', f'i32.const {SHADOW_BYTES - 4}', 'i32.gt_u',
         'if', 'unreachable', 'end',
         f'i32.const {SHADOW_BASE}',
         'global.get $shadow_off', 'i32.add', f'local.get ${name}', 'i32.store',
         'global.get $shadow_off', 'i32.const 4', 'i32.add', 'global.set $shadow_off']
    )


def shadow_restore_lines(depth_local: str) -> List[str]:
    return [f'local.get ${depth_local}', 'global.set $shadow_off']
