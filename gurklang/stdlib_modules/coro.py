from typing import List, TypeVar, Tuple
from ..builtin_utils import Module, Fail, make_simple, vec_to_stack, stack_to_vec
from ..types import CallByValue, Code, CodeFlags, Instruction, Put, Value, Stack, Scope


module = Module("coro")
T, V, S = Tuple, Value, Stack
Z = TypeVar("Z", bound=Stack)


@make_simple()
def __iterate(stack: T[V, T[V, S]], scope: Scope, fail: Fail):
    (initial, (fn, rest)) = stack
    initial_stack_vec = vec_to_stack(initial, fail)

    @make_simple()
    def __set_resulting_stack(resulting_stack: Stack, resulting_scope: Scope, _: Fail):
        stack_vec = stack_to_vec(resulting_stack)
        return (stack_vec, (fn, rest)), resulting_scope

    instructions: List[Instruction] = [
        Put(restore_stack((fn, initial_stack_vec))),    # stack: restore_stack(...)
        CallByValue(),                                  # stack: (fn, (initial_stack_vec, None))
        CallByValue(),                                  # stack: resulting stack
        Put(__set_resulting_stack),                     # stack: (__set_resulting_stack)
        CallByValue()                                   # stack: (resulting Vec, (fn, rest))
    ]
    code = Code(instructions, closure=None, flags=CodeFlags.PARENT_SCOPE, name="--iterate")
    return (code, rest), scope


module.add("iterate",
    Code(
        [Put(__iterate), CallByValue(), CallByValue()],
        closure=None,
        flags=CodeFlags.PARENT_SCOPE,
        name="--iterate",
    )
)


def restore_stack(stack: Stack):
    @make_simple()
    def __restore_stack(__stack: Stack, scope: Scope, fail: Fail):
        return stack, scope
    return __restore_stack
