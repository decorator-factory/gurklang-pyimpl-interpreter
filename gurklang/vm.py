from immutables import Map
from typing import Callable, Dict, Optional, Sequence, Union, Tuple
from . import prelude
from gurklang.types import (
    CallByValue, CodeFlags, MakeScope, NativeFunction, PopScope, Put,
    Scope, Stack, Instruction, Code, State, Value, Vec
)
from collections import deque
import threading


MiddlewareT = Callable[[Instruction, Stack, Stack], None]


_SCOPE_ID_LOCK = threading.Lock()
_SCOPE_ID = 0
def generate_scope_id():
    global _SCOPE_ID
    _SCOPE_ID_LOCK.__enter__
    with _SCOPE_ID_LOCK:
        _SCOPE_ID += 1
    return _SCOPE_ID


def make_scope(parent: Optional[Scope]) -> Scope:
    return Scope(parent, generate_scope_id(), Map())


def _load_function(scope: Scope, pipe: "deque[Instruction]", function: Union[Code, NativeFunction]):
    if function.tag == "native":
        pipe.append(CallByValue())
        pipe.append(Put(function))
    elif function.flags & CodeFlags.PARENT_SCOPE:
        pipe.extend(reversed(function.instructions))
    else:
        pipe.append(PopScope())
        pipe.extend(reversed(function.instructions))
        pipe.append(MakeScope(scope.join_closure_scope(function.closure)))


def call(state: State, function: Union[Code, NativeFunction]) -> State:
    """
    Stackless implementation of calling a function.

    Instructions are piped into a deque, from which they're popped
    and executed one by one.
    """
    return call_with_middleware(state, function, lambda _, __, ___: None)


def call_with_middleware(
    state: State,
    function: Union[Code, NativeFunction],
    middleware: MiddlewareT,
) -> State:
    """
    Like `call`, but execute some action on each change
    """
    pipe: "deque[Instruction]" = deque()

    # locked_boxes is a mapping between the box id and the previously held value in the box
    locked_boxes: Dict[int, Value] = {}

    _load_function(state.scope, pipe, function)

    while pipe:
        instruction = pipe.pop()

        old_state = state

        if instruction.tag == "call":
            pipe.append(CallByValue())
            pipe.append(Put(state.scope[instruction.function_name]))

        elif instruction.tag == "call_by_value":
            (function, stack) = state.stack  # type: ignore
            state = state.with_stack(stack)
            if function.tag == "code":
                _load_function(state.scope, pipe, function)
            else:
                state = function.fn(state)

        else:
            stack, scope = execute(state.stack, state.scope, instruction)
            state = state.with_stack(stack).with_scope(scope)

        middleware(instruction, old_state.stack, state.stack)

    if locked_boxes != {}:
        ids = tuple(locked_boxes)
        raise RuntimeError(f"The main loop has ended, but boxes {ids} are still locked")

    return state



def execute(stack: Stack, scope: Scope, instruction: Instruction) -> Tuple[Stack, Scope]:
    """
    Execute an instruction and return new state of the system.

    Pure function, i.e. doesn't perform any side effects.
    """
    if instruction.tag == "put":
        return (instruction.value, stack), scope

    elif instruction.tag == "put_code":
        return (Code(instruction.instructions, scope, source_code=instruction.source_code), stack), scope

    elif instruction.tag == "make_vec":
        elements = []
        for _ in range(instruction.size):
            head, stack = stack  # type: ignore
            elements.append(head)
        return (Vec(elements[::-1]), stack), scope

    elif instruction.tag == "make_scope":
        return stack, make_scope(instruction.parent)

    elif instruction.tag == "pop_scope":
        return stack, scope.parent  # type: ignore

    else:
        raise RuntimeError(instruction)


builtin_scope = prelude.module.make_scope(generate_scope_id())
global_scope = make_scope(parent=builtin_scope)


def run(instructions: Sequence[Instruction]):
    return call(
        State(None, global_scope, Map(), Map(), 0),
        Code(instructions, closure=None, name="<entry-point>")
    )


def run_with_middleware(instructions: Sequence[Instruction], middleware: MiddlewareT):
    return call_with_middleware(
        State(None, global_scope, Map(), Map(), 0),
        Code(instructions, closure=None, name="<entry-point>"),
        middleware
    )
