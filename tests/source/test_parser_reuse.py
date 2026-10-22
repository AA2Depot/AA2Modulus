"""Observable parser isolation across sequential and concurrent operations."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap

from tests.support.paths import ROOT


def test_first_concurrent_compilations_keep_parser_and_scope_state_independent():
    # A fresh interpreter exercises first use without resetting private caches.
    script = textwrap.dedent("""
        import json
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from tests.support.source import parse_module
        from aa2modulus.semantics.binding.state import SourceBindingError
        from aa2modulus.syntax.parser.errors import SourceParseError

        ready = Barrier(8)
        def compile_one(index):
            filename = f"cold-{index}.aa2m"
            source = (f'module "M{index}" {{ trigger "T" {{ '
                      f'let local_{index}: int = {index}; local_{index} = {index + 1}; }} }}')
            ready.wait()
            module = parse_module(source, filename=filename)
            try:
                parse_module('module "Broken" {', filename=filename)
            except SourceParseError as error:
                syntax_filename = error.filename
            else:
                raise AssertionError("invalid syntax accepted")
            unbound = f'module "Other" {{ trigger "T" {{ let copy: int = local_{index}; }} }}'
            try:
                parse_module(unbound, filename=filename)
            except SourceBindingError as error:
                assert error.diagnostic.code == "UNKNOWN_EXPRESSION_NAME"
                assert error.diagnostic.filename == filename
                assert (error.diagnostic.line, error.diagnostic.column) == (
                    1, unbound.index(f"local_{index}") + 1)
            else:
                raise AssertionError("local leaked into the next operation")
            variable = module.triggers[0].variables[0]
            assignment = module.triggers[0].gui_actions[0].action
            assert assignment.id == 1
            assert assignment.parameters[0].variable_name == variable.name
            assert assignment.parameters[1].constant.value == index + 1
            return (module.name, variable.name, variable.default_expression.constant.value,
                    module.source_span.filename, syntax_filename)
        with ThreadPoolExecutor(max_workers=8) as pool:
            print(json.dumps(list(pool.map(compile_one, range(8)))))
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [
        [f"M{index}", f"local_{index}", index, f"cold-{index}.aa2m", f"cold-{index}.aa2m"]
        for index in range(8)
    ]
