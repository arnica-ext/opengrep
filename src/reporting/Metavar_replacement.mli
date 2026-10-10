type replacement_ctx

(* for abstract_content and subpatterns matching-explanations
 * TODO: should not use! the result may miss some commas
 *)
val metavar_string_of_any : AST_generic.any -> string

(* Original capture representation, for JSON output and fingerprints only. *)
val metavar_abstract_content : ?lang:Lang.t -> AST_generic.any -> string
val original_for_reporting : AST_generic.any -> AST_generic.any

val of_bindings :
  ?for_reporting:bool ->
  ?metavar_lang:(string -> Lang.t option) ->
  Metavariable.bindings ->
  replacement_ctx

val of_out : Semgrep_output_v1_t.metavars -> replacement_ctx
val interpolate_metavars : string -> replacement_ctx -> string
