# Diagnostic codes

Every finding has a severity (`error`, `warning` or `info`) and a code, shown as
`error[CODE]`. An error stops compilation. A warning does not.

Editors link each code to its row on this page. Codes are grouped by the
stage that reports them. Names in `{...}` stand for
the parts the message fills in.

## Syntax

| Code | Meaning |
| --- | --- |
| <a id="SYNTAX_ERROR"></a>`SYNTAX_ERROR` | The text does not match the grammar. The help line often names the fix. |
| <a id="SOURCE_SYNTAX_ERROR_LIMIT"></a>`SOURCE_SYNTAX_ERROR_LIMIT` | More syntax errors than `--max-syntax-errors`; the rest are not listed. |
| <a id="INVALID_NUMBER"></a>`INVALID_NUMBER` | A number literal cannot be read. |
| <a id="INVALID_STRING"></a>`INVALID_STRING` | A string literal has an invalid escape sequence. |
| <a id="INVALID_SOURCE_NAME"></a>`INVALID_SOURCE_NAME` | A qualified name (`A.B`) appears where only a plain name is allowed. |
| <a id="MODULE_REQUIRED"></a>`MODULE_REQUIRED` | A `.aa2m` file has no `module` declaration. |
| <a id="LIBRARY_MODULE"></a>`LIBRARY_MODULE` | A `.aa2mi` library declares a `module`; libraries cannot. |
| <a id="TEMPLATE_LIBRARY_ONLY"></a>`TEMPLATE_LIBRARY_ONLY` | A trigger template appears outside a library. |
| <a id="ALLOW_UNIT_REQUIRED"></a>`ALLOW_UNIT_REQUIRED` | Internal: source with `@allow` reached a parser entry point that does not support it. Report it as a bug. |
| <a id="PAYLOAD_MISMATCH"></a>`PAYLOAD_MISMATCH` | A raw expression's payload does not fit its expression ID. |

## Imports

| Code | Meaning |
| --- | --- |
| <a id="IMPORT_PATH"></a>`IMPORT_PATH` | An import is not a `.aa2mi` path, or the path cannot be resolved. |
| <a id="IMPORT_READ_ERROR"></a>`IMPORT_READ_ERROR` | A library file cannot be read. |
| <a id="IMPORT_ENCODING"></a>`IMPORT_ENCODING` | A library file is not valid UTF-8. |
| <a id="IMPORT_CYCLE"></a>`IMPORT_CYCLE` | Libraries import each other in a cycle. |
| <a id="IMPORT_FILE_LIMIT"></a>`IMPORT_FILE_LIMIT` | More distinct libraries than `--max-import-files`. |
| <a id="IMPORT_DEPTH_LIMIT"></a>`IMPORT_DEPTH_LIMIT` | An import chain is deeper than `--max-import-depth`. |
| <a id="IMPORT_SIZE_LIMIT"></a>`IMPORT_SIZE_LIMIT` | The module and its libraries exceed `--max-total-source-chars`. |
| <a id="IMPORT_RESOLVER_REQUIRED"></a>`IMPORT_RESOLVER_REQUIRED` | Source with imports was given without a base folder; the CLI and editor always supply one. |

## Names and types

| Code | Meaning |
| --- | --- |
| <a id="UNKNOWN_ACTION_NAME"></a>`UNKNOWN_ACTION_NAME` | No action has this name, or several do. |
| <a id="UNKNOWN_EVENT_NAME"></a>`UNKNOWN_EVENT_NAME` | No event has this name, or several do. |
| <a id="UNKNOWN_EXPRESSION_NAME"></a>`UNKNOWN_EXPRESSION_NAME` | No expression, variable or constant has this name. |
| <a id="UNKNOWN_MEMBER"></a>`UNKNOWN_MEMBER` | The receiver has no member with this name. |
| <a id="UNKNOWN_OPERATOR_OVERLOAD"></a>`UNKNOWN_OPERATOR_OVERLOAD` | No operator overload, or more than one, fits these operand types. |
| <a id="AMBIGUOUS_EXPRESSION_NAME"></a>`AMBIGUOUS_EXPRESSION_NAME` | A name matches several expressions and the context cannot choose. |
| <a id="AMBIGUOUS_EXPRESSION_CALL"></a>`AMBIGUOUS_EXPRESSION_CALL` | A call matches several overloads and the argument types cannot choose. |
| <a id="AMBIGUOUS_MEMBER"></a>`AMBIGUOUS_MEMBER` | A member call matches several overloads. |
| <a id="AMBIGUOUS_NAMED_CONSTANT"></a>`AMBIGUOUS_NAMED_CONSTANT` | A constant name matches several native constants. |
| <a id="AMBIGUOUS_CONST"></a>`AMBIGUOUS_CONST` | A name is both a compile-time constant and a variable; write `const("...")` or `variable("...")`. |
| <a id="REJECTED_CONSTANT_NAME"></a>`REJECTED_CONSTANT_NAME` | A native constant name cannot select its row's value; the help names the verified spelling. |
| <a id="ACTION_ARITY"></a>`ACTION_ARITY` | An action call has the wrong number of arguments. |
| <a id="EVENT_ARITY"></a>`EVENT_ARITY` | An event has the wrong number of arguments. |
| <a id="EXPRESSION_ARITY"></a>`EXPRESSION_ARITY` | An expression call has the wrong number of arguments. |
| <a id="MEMBER_ARITY"></a>`MEMBER_ARITY` | A member call has the wrong number of arguments. |
| <a id="MEMBER_KIND"></a>`MEMBER_KIND` | A property is called with parentheses, or a method without them. |
| <a id="MEMBER_ACTION_BLOCK"></a>`MEMBER_ACTION_BLOCK` | A member action is given a `{ ... }` block. |
| <a id="SOURCE_TYPE_MISMATCH"></a>`SOURCE_TYPE_MISMATCH` | A value has the wrong type for where it is used, such as an `int` where a `card` is expected. |
| <a id="INT_OUT_OF_RANGE"></a>`INT_OUT_OF_RANGE` | An integer literal is outside the 32-bit signed range. |
| <a id="FLOAT_OUT_OF_RANGE"></a>`FLOAT_OUT_OF_RANGE` | A float literal is outside the 32-bit float range. |
| <a id="INVALID_LITERAL"></a>`INVALID_LITERAL` | A literal value is not supported here. |
| <a id="UNDEFINED_VARIABLE"></a>`UNDEFINED_VARIABLE` | A variable is used but not declared. The help names a global declaration to add; `decompile` reports it as a warning. |
| <a id="PROTECTED_NAME"></a>`PROTECTED_NAME` | `ThisCard` or `TriggeringCard` is declared or assigned. |
| <a id="INVALID_LOOP_CONTROL"></a>`INVALID_LOOP_CONTROL` | `break` or `continue` is used outside a loop. |
| <a id="FOR_LOOP_TARGET_TYPE"></a>`FOR_LOOP_TARGET_TYPE` | A `for` loop variable is not an `int` (or `card`). |
| <a id="UNSUPPORTED_EXPRESSION"></a>`UNSUPPORTED_EXPRESSION` | The expression form is not supported. |
| <a id="UNSUPPORTED_STATEMENT"></a>`UNSUPPORTED_STATEMENT` | The statement form is not supported. |
| <a id="SOURCE_BINDING_ERROR_LIMIT"></a>`SOURCE_BINDING_ERROR_LIMIT` | More name and type errors than `--max-binding-errors`. |

## Constants

| Code | Meaning |
| --- | --- |
| <a id="UNDEFINED_CONST"></a>`UNDEFINED_CONST` | A constant is used but not declared, or is declared somewhere it is not visible. |
| <a id="DUPLICATE_CONST"></a>`DUPLICATE_CONST` | A constant is declared twice in the same scope. |
| <a id="CONST_CYCLE"></a>`CONST_CYCLE` | Constants refer to each other in a cycle. |
| <a id="CONST_TYPE"></a>`CONST_TYPE` | A constant's type is not `int`, `bool`, `float` or `string`. |
| <a id="CONST_NAME"></a>`CONST_NAME` | A constant name is empty. |
| <a id="CONST_NAME_COLLISION"></a>`CONST_NAME_COLLISION` | A declaration reuses the name of a visible constant. |
| <a id="CONST_ASSIGNMENT"></a>`CONST_ASSIGNMENT` | Code tries to assign to a constant. |

## Macros

| Code | Meaning |
| --- | --- |
| <a id="DUPLICATE_MACRO"></a>`DUPLICATE_MACRO` | Two macros have the same name. |
| <a id="DUPLICATE_MACRO_PARAMETER"></a>`DUPLICATE_MACRO_PARAMETER` | A macro declares a parameter twice. |
| <a id="MACRO_NAME"></a>`MACRO_NAME` | A macro name is not valid. |
| <a id="MACRO_PARAMETER_NAME"></a>`MACRO_PARAMETER_NAME` | A macro parameter name is not valid. |
| <a id="MACRO_PARAMETER_TYPE"></a>`MACRO_PARAMETER_TYPE` | A macro parameter type is not `card`, `int`, `bool`, `float` or `string`. |
| <a id="MACRO_ACTION_COLLISION"></a>`MACRO_ACTION_COLLISION` | A macro has the name of a built-in action. |
| <a id="MACRO_ARITY"></a>`MACRO_ARITY` | A macro call has the wrong number of arguments. |
| <a id="MACRO_CALL_BLOCK"></a>`MACRO_CALL_BLOCK` | A macro call is given a block instead of ending with `;`. |
| <a id="MACRO_CAPTURE"></a>`MACRO_CAPTURE` | A macro uses a variable from where it is called instead of a parameter. |
| <a id="MACRO_PARAMETER_WRITE"></a>`MACRO_PARAMETER_WRITE` | A macro assigns to one of its parameters. |
| <a id="MACRO_LOOP_SCOPE"></a>`MACRO_LOOP_SCOPE` | `break` or `continue` in a macro has no loop inside that macro. |
| <a id="MACRO_CYCLE"></a>`MACRO_CYCLE` | Macros call each other recursively. |
| <a id="MACRO_DEPTH_LIMIT"></a>`MACRO_DEPTH_LIMIT` | Macro calls nest deeper than `--max-macro-depth`. |

## Trigger templates

| Code | Meaning |
| --- | --- |
| <a id="UNKNOWN_TEMPLATE"></a>`UNKNOWN_TEMPLATE` | `import.trigger` names a template that no imported library defines. |
| <a id="DUPLICATE_TEMPLATE"></a>`DUPLICATE_TEMPLATE` | Two templates have the same name. |
| <a id="TEMPLATE_NAME"></a>`TEMPLATE_NAME` | A template name is empty. |
| <a id="TEMPLATE_TRIGGER_NAME"></a>`TEMPLATE_TRIGGER_NAME` | An instantiated trigger name is empty. |
| <a id="TEMPLATE_TRIGGER_NAME_COLLISION"></a>`TEMPLATE_TRIGGER_NAME_COLLISION` | An instantiated trigger has the name of another trigger. |
| <a id="UNKNOWN_SLOT"></a>`UNKNOWN_SLOT` | An instantiation binds a slot the template does not have. |
| <a id="MISSING_SLOT"></a>`MISSING_SLOT` | An instantiation leaves a required slot unbound. |
| <a id="DUPLICATE_SLOT_BINDING"></a>`DUPLICATE_SLOT_BINDING` | An instantiation binds a slot twice. |
| <a id="DUPLICATE_TEMPLATE_SLOT"></a>`DUPLICATE_TEMPLATE_SLOT` | A template declares a slot twice. |
| <a id="TEMPLATE_SLOT_NAME"></a>`TEMPLATE_SLOT_NAME` | A slot name is not valid. |
| <a id="TEMPLATE_SLOT_TYPE"></a>`TEMPLATE_SLOT_TYPE` | A slot type is not `card`, `int`, `bool`, `float` or `string`. |
| <a id="TEMPLATE_SLOT_WRITE"></a>`TEMPLATE_SLOT_WRITE` | A template assigns to a value slot. |
| <a id="TEMPLATE_SLOT_RAW_REFERENCE"></a>`TEMPLATE_SLOT_RAW_REFERENCE` | A raw variable reference names a value slot. |
| <a id="TEMPLATE_SLOT_LOCAL_COLLISION"></a>`TEMPLATE_SLOT_LOCAL_COLLISION` | A template local has the name of a slot. |
| <a id="TEMPLATE_CAPTURE"></a>`TEMPLATE_CAPTURE` | A template assigns to a variable it does not declare. |
| <a id="TEMPLATE_LOOP_SCOPE"></a>`TEMPLATE_LOOP_SCOPE` | `break` or `continue` in a template has no loop inside that template. |

## `@allow`

| Code | Meaning |
| --- | --- |
| <a id="NATIVE_HAZARD_ALLOWED"></a>`NATIVE_HAZARD_ALLOWED` | Warning: an `@allow` turned a known AAUnlimited hazard into a warning. |
| <a id="ALLOW_NOT_PERMITTED"></a>`ALLOW_NOT_PERMITTED` | `@allow` names a code that cannot be acknowledged. |
| <a id="UNUSED_ALLOW"></a>`UNUSED_ALLOW` | `@allow` acknowledges nothing in the item it prefixes. |

## Module validation

These come from checking the compiled module. `decompile` and `inspect` report
them for binary modules too.

| Code | Meaning |
| --- | --- |
| <a id="UNKNOWN_ACTION"></a>`UNKNOWN_ACTION` | An action ID is not in the registry. |
| <a id="UNKNOWN_EVENT"></a>`UNKNOWN_EVENT` | An event ID is not in the registry. |
| <a id="UNKNOWN_EXPRESSION"></a>`UNKNOWN_EXPRESSION` | An expression ID is not in the registry for its return type. |
| <a id="UNKNOWN_NAMED_CONSTANT"></a>`UNKNOWN_NAMED_CONSTANT` | A named-constant ID is not in the registry for its type. |
| <a id="ACTION_PARAMETER_TYPE"></a>`ACTION_PARAMETER_TYPE` | An action argument has the wrong type. |
| <a id="EVENT_PARAMETER_TYPE"></a>`EVENT_PARAMETER_TYPE` | An event argument has the wrong type. |
| <a id="EXPRESSION_PARAMETER_TYPE"></a>`EXPRESSION_PARAMETER_TYPE` | An expression argument has the wrong type. |
| <a id="INVALID_EXPRESSION_RETURN_TYPE"></a>`INVALID_EXPRESSION_RETURN_TYPE` | An expression has an invalid return type. |
| <a id="INVALID_VALUE_TYPE"></a>`INVALID_VALUE_TYPE` | A value has an invalid type. |
| <a id="INVALID_VARIABLE_TYPE"></a>`INVALID_VARIABLE_TYPE` | A variable has an invalid type. |
| <a id="NAMED_CONSTANT_TYPE_MISMATCH"></a>`NAMED_CONSTANT_TYPE_MISMATCH` | A named constant's type does not match where it is used. |
| <a id="CONSTANT_TYPE_MISMATCH"></a>`CONSTANT_TYPE_MISMATCH` | A constant value's type does not match where it is used. |
| <a id="VARIABLE_TYPE_MISMATCH"></a>`VARIABLE_TYPE_MISMATCH` | A variable's type does not match where it is used. |
| <a id="VARIABLE_DEFAULT_TYPE"></a>`VARIABLE_DEFAULT_TYPE` | A local variable's default value has the wrong type. |
| <a id="GLOBAL_DEFAULT_TYPE"></a>`GLOBAL_DEFAULT_TYPE` | A global variable's default value has the wrong type. |
| <a id="GLOBAL_CURRENT_TYPE"></a>`GLOBAL_CURRENT_TYPE` | A global variable's current value has the wrong type. |
| <a id="ASSIGNMENT_TYPE_MISMATCH"></a>`ASSIGNMENT_TYPE_MISMATCH` | An assignment stores a value of the wrong type. |
| <a id="ASSIGNMENT_DECLARATION_TYPE"></a>`ASSIGNMENT_DECLARATION_TYPE` | An assignment stores a type that differs from the declaration; AAUnlimited does not check this. |
| <a id="INVALID_ASSIGNMENT_TARGET"></a>`INVALID_ASSIGNMENT_TARGET` | An assignment target is not a variable. |
| <a id="DUPLICATE_GLOBAL_VARIABLE"></a>`DUPLICATE_GLOBAL_VARIABLE` | A global variable is declared twice. |
| <a id="DUPLICATE_LOCAL_VARIABLE"></a>`DUPLICATE_LOCAL_VARIABLE` | A local variable is declared twice in one trigger. |
| <a id="INVALID_MODULE_DEPENDENCY"></a>`INVALID_MODULE_DEPENDENCY` | A `depends_on` name is empty or names the module itself. |
| <a id="DUPLICATE_MODULE_DEPENDENCY"></a>`DUPLICATE_MODULE_DEPENDENCY` | A `depends_on` name is listed twice. |

## AAUnlimited hazards

These describe how AAUnlimited itself behaves. Some can be acknowledged with
`@allow` (see the [language reference](../language-contract.md#acknowledging-native-hazards)).

| Code | Meaning |
| --- | --- |
| <a id="NATIVE_DEFECTIVE_EXPRESSION"></a>`NATIVE_DEFECTIVE_EXPRESSION` | The expression cannot work in AAUnlimited, for example `Text.Replace`. |
| <a id="REVIEWED_VALUE_TYPE_MISMATCH"></a>`REVIEWED_VALUE_TYPE_MISMATCH` | An event-dependent value is read in an event where AAUnlimited returns another type. |
| <a id="REVIEWED_VALUE_CONTEXT_UNKNOWN"></a>`REVIEWED_VALUE_CONTEXT_UNKNOWN` | An event-dependent value is read in a trigger whose events are not all known. |
| <a id="EXPRESSION_METADATA_RETURN_TYPE_MISMATCH"></a>`EXPRESSION_METADATA_RETURN_TYPE_MISMATCH` | An expression is used in a type scope that differs from its native declaration. |
| <a id="NATIVE_EXPRESSION_RESAVE_TYPE_CHANGE"></a>`NATIVE_EXPRESSION_RESAVE_TYPE_CHANGE` | AAUnlimited would change the expression's type when it saves and reloads the module. |
| <a id="NATIVE_DISCARDED_CONTROL"></a>`NATIVE_DISCARDED_CONTROL` | AAUnlimited drops this `break` or `continue` because no loop is active there. |
| <a id="NATIVE_PROJECTION_ERROR"></a>`NATIVE_PROJECTION_ERROR` | The action tree cannot be laid out the way AAUnlimited loads it. |

## Source limits

| Code | Meaning |
| --- | --- |
| <a id="SOURCE_SIZE_LIMIT"></a>`SOURCE_SIZE_LIMIT` | A file is longer than `--max-source-chars`. |
| <a id="SOURCE_NODE_LIMIT"></a>`SOURCE_NODE_LIMIT` | A stage has more nodes than `--max-source-nodes`. |
| <a id="SOURCE_DEPTH_LIMIT"></a>`SOURCE_DEPTH_LIMIT` | Syntax nests deeper than `--max-syntax-depth`. |
| <a id="SOURCE_NESTING_LIMIT"></a>`SOURCE_NESTING_LIMIT` | Statements or expressions nest deeper than `--max-source-nesting`. |
| <a id="SOURCE_BINDING_WORK_LIMIT"></a>`SOURCE_BINDING_WORK_LIMIT` | Name and overload resolution exceeds `--max-binding-work`. |
| <a id="EDITOR_RECOVERY_LIMIT"></a>`EDITOR_RECOVERY_LIMIT` | The editor gave up recovering a file with too many syntax faults. |

## Binary modules

| Code | Meaning |
| --- | --- |
| <a id="DECODE_ERROR"></a>`DECODE_ERROR` | The file is not a valid AAUnlimited module. |
| <a id="BINARY_ERROR"></a>`BINARY_ERROR` | A binary record cannot be read or written. |
| <a id="TRAILING_BYTES"></a>`TRAILING_BYTES` | Warning: bytes follow the module data. Decompiled source does not keep them. |
| <a id="RAW_FALLBACK"></a>`RAW_FALLBACK` | Warning: part of a module was decompiled as raw syntax. The message gives the reason. |
| <a id="WRITE_ERROR"></a>`WRITE_ERROR` | The compiled module cannot be encoded, for example a value too large for its field. |
| <a id="LIBRARY_COMPILE"></a>`LIBRARY_COMPILE` | A `.aa2mi` library was given to `compile`; only modules compile. |

## Editor commands

The language server's compile and decompile commands report these.

| Code | Meaning |
| --- | --- |
| <a id="COMPILE_DOCUMENT_REQUIRED"></a>`COMPILE_DOCUMENT_REQUIRED` | The module to compile is not open. |
| <a id="COMPILE_FILE_REQUIRED"></a>`COMPILE_FILE_REQUIRED` | The module is not saved as a `.aa2m` file. |
| <a id="COMPILE_OUTPUT_SOURCE"></a>`COMPILE_OUTPUT_SOURCE` | The output path would overwrite a source file. |
| <a id="COMPILE_SOURCE_CHANGED"></a>`COMPILE_SOURCE_CHANGED` | A source file changed during compilation; try again. |
| <a id="SOURCE_READ_ERROR"></a>`SOURCE_READ_ERROR` | A source file cannot be read. |
| <a id="SOURCE_ENCODING"></a>`SOURCE_ENCODING` | A source file is not valid UTF-8. |
| <a id="OUTPUT_WRITE_ERROR"></a>`OUTPUT_WRITE_ERROR` | The compiled module cannot be written. |
| <a id="DECOMPILE_ERROR"></a>`DECOMPILE_ERROR` | The module cannot be decompiled. |
