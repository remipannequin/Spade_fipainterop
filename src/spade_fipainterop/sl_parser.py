sl_grammar = r"""

start: acl_message

// ---------------- ACL MESSAGE ----------------

acl_message: "(" performative keyword_term* ")"

performative: SYMBOL_SIMPLE

?value: term
      | collection
      | proposition
      | action_expr
      | acl_message

// ---------------- PROPOSITIONS LOGIQUES ----------------

collection: "(" "set" term* ")"
          | "(" "sequence" term* ")"

?proposition: atomic_formula
            | "(" "not" proposition ")"
            | "(" "and" proposition proposition+ ")"
            | "(" "or" proposition proposition+ ")"
            | "(" "implies" proposition proposition ")"
            | "(" "equiv" proposition proposition ")"
            | "(" "forall" "(" variable+ ")" proposition ")"
            | "(" "exists" "(" variable+ ")" proposition ")"
            | "(" "bel" agent proposition ")"
            | "(" "goal" agent proposition ")"
            | "(" "=" term term ")"

// ---------------- ATOMIC FORMULAS ----------------

atomic_formula: "(" predicate term* ")"

// ---------------- ACTION EXPRESSIONS ----------------

?action_expr: "(" "action" agent action_term ")"
            | "(" "done" action_expr ")"
            | "(" "feasible" action_expr ")"

action_term: "(" function_symbol term* ")"

// ---------------- TERMS ----------------

?term: keyword_term
     | simple_term

?keyword_term: KEYWORD simple_term

?simple_term: constant
            | variable
            | collection
            | function

function: "(" function_symbol term* ")"

// ---------------- SYMBOLIC ELEMENTS ----------------

predicate: SYMBOL_SIMPLE
function_symbol: SYMBOL_SIMPLE
agent: AGENTID

constant: SYMBOL_SIMPLE
        | AGENTID
        | STRING
        | NUMBER
        | DATETIME

variable: "?" SYMBOL_SIMPLE

// ---------------- LEXER ----------------

KEYWORD: ":" /[a-zA-Z_][a-zA-Z0-9_-]*/      // mots-clés ACL
AGENTID: /[a-zA-Z_][a-zA-Z0-9_\-@:\/\.]*/    // identifiants d’agents et URIs
SYMBOL_SIMPLE: /[a-zA-Z_][a-zA-Z0-9_-]*/  // variables et symboles logiques simples
DATETIME: /\d{8}T\d{6,9}Z/  // format ISO 8601 pour les dates

STRING: ESCAPED_STRING
NUMBER: SIGNED_NUMBER

%import common.ESCAPED_STRING
%import common.SIGNED_NUMBER
%import common.WS
%ignore WS

"""