# Diagnostic codes

Every finding has a severity (`error`, `warning` or `info`) and a code, shown as
`error[CODE]`. An error stops compilation. A warning does not.

Codes are grouped by the stage that reports them. Names in `{...}` stand for
the parts the message fills in.

## Syntax

| Code | Meaning |
| --- | --- |
| `SYNTAX_ERROR` | The text does not match the grammar. The help line often names the fix. |
| `SOURCE_SYNTAX_ERROR_LIMIT` | More syntax errors than `--max-syntax-errors`; the rest are not listed. |
| `INVALID_NUMBER` | A number literal cannot be read. |
| `INVALID_STRING` | A string literal has an invalid escape sequence. |
| `INVALID_SOURCE_NAME` | A qualified name (`A.B`) appears where only a plain name is allowed. |
| `MODULE_REQUIRED` | A `.aa2m` file has no `module` declaration. |
| `LIBRARY_MODULE` | A `.aa2mi` library declares a `module`; libraries cannot. |
| `TEMPLATE_LIBRARY_ONLY` | A trigger template appears outside a library. |
| `ALLOW_UNIT_REQUIRED` | Internal: source with `@allow` reached a parser entry point that does not support it. Report it as a bug. |
| `PAYLOAD_MISMATCH` | A raw expression's payload does not fit its expression ID. |

## Imports

| Code | Meaning |
| --- | --- |
| `IMPORT_PATH` | An import is not a `.aa2mi` path, or the path cannot be resolved. |
| `IMPORT_READ_ERROR` | A library file cannot be read. |
| `IMPORT_ENCODING` | A library file is not valid UTF-8. |
| `IMPORT_CYCLE` | Libraries import each other in a cycle. |
| `IMPORT_FILE_LIMIT` | More distinct libraries than `--max-import-files`. |
| `IMPORT_DEPTH_LIMIT` | An import chain is deeper than `--max-import-depth`. |
| `IMPORT_SIZE_LIMIT` | The module and its libraries exceed `--max-total-source-chars`. |
| `IMPORT_RESOLVER_REQUIRED` | Source with imports was given without a base folder; the CLI and editor always supply one. |

## Names and types

| Code | Meaning |
| --- | --- |
| `UNKNOWN_ACTION_NAME` | No action has this name, or several do. |
| `UNKNOWN_EVENT_NAME` | No event has this name, or several do. |
| `UNKNOWN_EXPRESSION_NAME` | No expression, variable or constant has this name. |
| `UNKNOWN_MEMBER` | The receiver has no member with this name. |
| `UNKNOWN_OPERATOR_OVERLOAD` | No operator overload, or more than one, fits these operand types. |
| `AMBIGUOUS_EXPRESSION_NAME` | A name matches several expressions and the context cannot choose. |
| `AMBIGUOUS_EXPRESSION_CALL` | A call matches several overloads and the argument types cannot choose. |
| `AMBIGUOUS_MEMBER` | A member call matches several overloads. |
| `AMBIGUOUS_NAMED_CONSTANT` | A constant name matches several native constants. |
| `AMBIGUOUS_CONST` | A name is both a compile-time constant and a variable; write `const("...")` or `variable("...")`. |
| `REJECTED_CONSTANT_NAME` | A native constant name cannot select its row's value; the help names the verified spelling. |
| `ACTION_ARITY` | An action call has the wrong number of arguments. |
| `EVENT_ARITY` | An event has the wrong number of arguments. |
| `EXPRESSION_ARITY` | An expression call has the wrong number of arguments. |
| `MEMBER_ARITY` | A member call has the wrong number of arguments. |
| `MEMBER_KIND` | A property is called with parentheses, or a method without them. |
| `MEMBER_ACTION_BLOCK` | A member action is given a `{ ... }` block. |
| `SOURCE_TYPE_MISMATCH` | A value has the wrong type for where it is used, such as an `int` where a `card` is expected. |
| `INT_OUT_OF_RANGE` | An integer literal is outside the 32-bit signed range. |
| `FLOAT_OUT_OF_RANGE` | A float literal is outside the 32-bit float range. |
| `INVALID_LITERAL` | A literal value is not supported here. |
| `UNDEFINED_VARIABLE` | A variable is used but not declared. The help names a global declaration to add; `decompile` reports it as a warning. |
| `PROTECTED_NAME` | `ThisCard` or `TriggeringCard` is declared or assigned. |
| `INVALID_LOOP_CONTROL` | `break` or `continue` is used outside a loop. |
| `FOR_LOOP_TARGET_TYPE` | A `for` loop variable is not an `int` (or `card`). |
| `UNSUPPORTED_EXPRESSION` | The expression form is not supported. |
| `UNSUPPORTED_STATEMENT` | The statement form is not supported. |
| `SOURCE_BINDING_ERROR_LIMIT` | More name and type errors than `--max-binding-errors`. |

## Constants

| Code | Meaning |
| --- | --- |
| `UNDEFINED_CONST` | A constant is used but not declared, or is declared somewhere it is not visible. |
| `DUPLICATE_CONST` | A constant is declared twice in the same scope. |
| `CONST_CYCLE` | Constants refer to each other in a cycle. |
| `CONST_TYPE` | A constant's type is not `int`, `bool`, `float` or `string`. |
| `CONST_NAME` | A constant name is empty. |
| `CONST_NAME_COLLISION` | A declaration reuses the name of a visible constant. |
| `CONST_ASSIGNMENT` | Code tries to assign to a constant. |

## Macros

| Code | Meaning |
| --- | --- |
| `DUPLICATE_MACRO` | Two macros have the same name. |
| `DUPLICATE_MACRO_PARAMETER` | A macro declares a parameter twice. |
| `MACRO_NAME` | A macro name is not valid. |
| `MACRO_PARAMETER_NAME` | A macro parameter name is not valid. |
| `MACRO_PARAMETER_TYPE` | A macro parameter type is not `card`, `int`, `bool`, `float` or `string`. |
| `MACRO_ACTION_COLLISION` | A macro has the name of a built-in action. |
| `MACRO_ARITY` | A macro call has the wrong number of arguments. |
| `MACRO_CALL_BLOCK` | A macro call is given a block instead of ending with `;`. |
| `MACRO_CAPTURE` | A macro uses a variable from where it is called instead of a parameter. |
| `MACRO_PARAMETER_WRITE` | A macro assigns to one of its parameters. |
| `MACRO_LOOP_SCOPE` | `break` or `continue` in a macro has no loop inside that macro. |
| `MACRO_CYCLE` | Macros call each other recursively. |
| `MACRO_DEPTH_LIMIT` | Macro calls nest deeper than `--max-macro-depth`. |

## Trigger templates

| Code | Meaning |
| --- | --- |
| `UNKNOWN_TEMPLATE` | `import.trigger` names a template that no imported library defines. |
| `DUPLICATE_TEMPLATE` | Two templates have the same name. |
| `TEMPLATE_NAME` | A template name is empty. |
| `TEMPLATE_TRIGGER_NAME` | An instantiated trigger name is empty. |
| `TEMPLATE_TRIGGER_NAME_COLLISION` | An instantiated trigger has the name of another trigger. |
| `UNKNOWN_SLOT` | An instantiation binds a slot the template does not have. |
| `MISSING_SLOT` | An instantiation leaves a required slot unbound. |
| `DUPLICATE_SLOT_BINDING` | An instantiation binds a slot twice. |
| `DUPLICATE_TEMPLATE_SLOT` | A template declares a slot twice. |
| `TEMPLATE_SLOT_NAME` | A slot name is not valid. |
| `TEMPLATE_SLOT_TYPE` | A slot type is not `card`, `int`, `bool`, `float` or `string`. |
| `TEMPLATE_SLOT_WRITE` | A template assigns to a value slot. |
| `TEMPLATE_SLOT_RAW_REFERENCE` | A raw variable reference names a value slot. |
| `TEMPLATE_SLOT_LOCAL_COLLISION` | A template local has the name of a slot. |
| `TEMPLATE_CAPTURE` | A template assigns to a variable it does not declare. |
| `TEMPLATE_LOOP_SCOPE` | `break` or `continue` in a template has no loop inside that template. |

## `@allow`

| Code | Meaning |
| --- | --- |
| `NATIVE_HAZARD_ALLOWED` | Warning: an `@allow` turned a known AAUnlimited hazard into a warning. |
| `ALLOW_NOT_PERMITTED` | `@allow` names a code that cannot be acknowledged. |
| `UNUSED_ALLOW` | `@allow` acknowledges nothing in the item it prefixes. |

## Module validation

These come from checking the compiled module. `decompile` and `inspect` report
them for binary modules too.

| Code | Meaning |
| --- | --- |
| `UNKNOWN_ACTION` | An action ID is not in the registry. |
| `UNKNOWN_EVENT` | An event ID is not in the registry. |
| `UNKNOWN_EXPRESSION` | An expression ID is not in the registry for its return type. |
| `UNKNOWN_NAMED_CONSTANT` | A named-constant ID is not in the registry for its type. |
| `ACTION_PARAMETER_TYPE` | An action argument has the wrong type. |
| `EVENT_PARAMETER_TYPE` | An event argument has the wrong type. |
| `EXPRESSION_PARAMETER_TYPE` | An expression argument has the wrong type. |
| `INVALID_EXPRESSION_RETURN_TYPE` | An expression has an invalid return type. |
| `INVALID_VALUE_TYPE` | A value has an invalid type. |
| `INVALID_VARIABLE_TYPE` | A variable has an invalid type. |
| `NAMED_CONSTANT_TYPE_MISMATCH` | A named constant's type does not match where it is used. |
| `CONSTANT_TYPE_MISMATCH` | A constant value's type does not match where it is used. |
| `VARIABLE_TYPE_MISMATCH` | A variable's type does not match where it is used. |
| `VARIABLE_DEFAULT_TYPE` | A local variable's default value has the wrong type. |
| `GLOBAL_DEFAULT_TYPE` | A global variable's default value has the wrong type. |
| `GLOBAL_CURRENT_TYPE` | A global variable's current value has the wrong type. |
| `ASSIGNMENT_TYPE_MISMATCH` | An assignment stores a value of the wrong type. |
| `ASSIGNMENT_DECLARATION_TYPE` | An assignment stores a type that differs from the declaration; AAUnlimited does not check this. |
| `INVALID_ASSIGNMENT_TARGET` | An assignment target is not a variable. |
| `DUPLICATE_GLOBAL_VARIABLE` | A global variable is declared twice. |
| `DUPLICATE_LOCAL_VARIABLE` | A local variable is declared twice in one trigger. |
| `INVALID_MODULE_DEPENDENCY` | A `depends_on` name is empty or names the module itself. |
| `DUPLICATE_MODULE_DEPENDENCY` | A `depends_on` name is listed twice. |

## AAUnlimited hazards

These describe how AAUnlimited itself behaves. Some can be acknowledged with
`@allow` (see the [language reference](../language-contract.md#acknowledging-native-hazards)).

| Code | Meaning |
| --- | --- |
| `NATIVE_DEFECTIVE_EXPRESSION` | The expression cannot work in AAUnlimited, for example `Text.Replace`. |
| `REVIEWED_VALUE_TYPE_MISMATCH` | An event-dependent value is read in an event where AAUnlimited returns another type. |
| `REVIEWED_VALUE_CONTEXT_UNKNOWN` | An event-dependent value is read in a trigger whose events are not all known. |
| `EXPRESSION_METADATA_RETURN_TYPE_MISMATCH` | An expression is used in a type scope that differs from its native declaration. |
| `NATIVE_EXPRESSION_RESAVE_TYPE_CHANGE` | AAUnlimited would change the expression's type when it saves and reloads the module. |
| `NATIVE_DISCARDED_CONTROL` | AAUnlimited drops this `break` or `continue` because no loop is active there. |
| `NATIVE_PROJECTION_ERROR` | The action tree cannot be laid out the way AAUnlimited loads it. |

## Source limits

| Code | Meaning |
| --- | --- |
| `SOURCE_SIZE_LIMIT` | A file is longer than `--max-source-chars`. |
| `SOURCE_NODE_LIMIT` | A stage has more nodes than `--max-source-nodes`. |
| `SOURCE_DEPTH_LIMIT` | Syntax nests deeper than `--max-syntax-depth`. |
| `SOURCE_NESTING_LIMIT` | Statements or expressions nest deeper than `--max-source-nesting`. |
| `SOURCE_BINDING_WORK_LIMIT` | Name and overload resolution exceeds `--max-binding-work`. |
| `EDITOR_RECOVERY_LIMIT` | The editor gave up recovering a file with too many syntax faults. |

## Binary modules

| Code | Meaning |
| --- | --- |
| `DECODE_ERROR` | The file is not a valid AAUnlimited module. |
| `BINARY_ERROR` | A binary record cannot be read or written. |
| `TRAILING_BYTES` | Warning: bytes follow the module data. Decompiled source does not keep them. |
| `RAW_FALLBACK` | Warning: part of a module was decompiled as raw syntax. The message gives the reason. |
| `WRITE_ERROR` | The compiled module cannot be encoded, for example a value too large for its field. |
| `LIBRARY_COMPILE` | A `.aa2mi` library was given to `compile`; only modules compile. |

## Editor commands

The language server's compile and decompile commands report these.

| Code | Meaning |
| --- | --- |
| `COMPILE_DOCUMENT_REQUIRED` | The module to compile is not open. |
| `COMPILE_FILE_REQUIRED` | The module is not saved as a `.aa2m` file. |
| `COMPILE_OUTPUT_SOURCE` | The output path would overwrite a source file. |
| `COMPILE_SOURCE_CHANGED` | A source file changed during compilation; try again. |
| `SOURCE_READ_ERROR` | A source file cannot be read. |
| `SOURCE_ENCODING` | A source file is not valid UTF-8. |
| `OUTPUT_WRITE_ERROR` | The compiled module cannot be written. |
| `DECOMPILE_ERROR` | The module cannot be decompiled. |
