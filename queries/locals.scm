
; Local variable scoping for SVL
(function_declaration
  (identifier) @local
  (parameter_list
    (parameter
      (identifier) @local)))

(lambda_expression
  (parameter_list
    (parameter
      (identifier) @local)))

(let_statement
  (identifier) @local)
