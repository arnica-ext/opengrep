(* Yoann Padioleau
 *
 * Copyright (C) 2019-2023 Semgrep Inc.
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public License
 * version 2.1 as published by the Free Software Foundation, with the
 * special exception on linking described in file LICENSE.
 *
 * This library is distributed in the hope that it will be useful, but
 * WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the file
 * LICENSE for more details.
 *)
module E = Core_error
module Out = Semgrep_output_v1_t
module PM = Core_match

(*****************************************************************************)
(* Prelude *)
(*****************************************************************************)

(*****************************************************************************)
(* Types *)
(*****************************************************************************)

(* Id of a single pattern in a formula. This will be used to generate
 * mini rules with this id, and later when we evaluate the formula, find
 * the matching results corresponding to this id.
 *)
type pattern_id = Xpattern.pattern_id
type id_to_match_results = (pattern_id, Core_match.t list ref) Hashtbl.t

(* alt: prefilter_cache option *)
type prefilter_config =
  | PrefilterWithCache of Analyze_rule.prefilter_cache
  | NoPrefiltering

(* eXtended config.
 * less: we might want to get rid of equivalences at some point as
 * they are not exposed to the user anymore.
 *)
type xconfig = {
  config : Rule_options.t; (* corresponds to rule `options` key *)
  equivs : Equivalence.equivalences;
  nested_formula : bool;
  legacy_elixir_captures : bool;
  matching_conf : Match_patterns.matching_conf;
  (* ^^^ i.e. we are evaluating a nested formula within `metavariable-pattern`. *)
  (* Fields coming from Runner_config.t used by the engine.
   * We could just include the whole Runner_config.t, but it's
   * cleaner to explicitely state what the engine depends on
   * (there's lots of fields in Runner_config.t).
   *)
  matching_explanations : bool;
  filter_irrelevant_rules : prefilter_config;

}

type env = {
  xconf : xconfig;
  pattern_matches : id_to_match_results;
  (* used by metavariable-pattern to recursively call evaluate_formula *)
  xtarget : Xtarget.t;
  rule : Rule.t;
  (* as-metavariable: This is here so we can easily pass down
     `has_as_metavariable` to `evaluate_formula`, which will dictate
     whether  we should set the `ast_node` field when focusing, as this is
     only needed for rules  making use of the `as-metavariable` feature.
  *)
  has_as_metavariable : bool;
  (* problems found during evaluation, one day these may be caught earlier by
   * the meta-checker *)
  errors : Core_error.ErrorSet.t ref;
}

(*****************************************************************************)
(* Helpers *)
(*****************************************************************************)

(* Report errors during evaluation to the user rather than just logging them
 * as we did before. *)
let error (env : env) msg =
  (* We are not supposed to report errors in the config file for several reasons
   * (one being that it's often a temporary file anyways), so we report them on
   * the target file. *)
  let loc = Tok.first_loc_of_file env.xtarget.path.internal_path_to_content in
  (* TODO: warning or error? MatchingError or ... ? *)
  let err = E.mk_error ~rule_id:(fst env.rule.id) ~msg ~loc Out.MatchingError in
  env.errors := Core_error.ErrorSet.add err !(env.errors)

(* this will be adjusted later in range_to_pattern_match_adjusted *)
let fake_rule_id (id, str) =
  {
    PM.id = Rule_ID.of_string_exn (string_of_int id);
    pattern_string = str;
    message = "";
    metadata = None;
    fix = None;
    fix_regexp = None;
    langs = [];
    options = None;
  }

let adjust_xconfig_with_rule_options xconf options =
  (* When rule options are present, we need to merge them with the existing config
   * rather than replace it entirely. This preserves command-line flags like
   * --taint-intrafile which are set in xconf.config. *)
  let config =
    match options with
    | None -> xconf.config
    | Some (rule_opts : Rule_options.t) ->
        (* Merge rule options with existing config, preserving command-line taint_intrafile setting *)
        { rule_opts with
          taint_intrafile = xconf.config.taint_intrafile || rule_opts.taint_intrafile;
          effect_guards = xconf.config.effect_guards || rule_opts.effect_guards
        }
  in
  { xconf with config }

let default_xconfig =
  {
    config = Rule_options.default;
    equivs = [];
    nested_formula = false;
    legacy_elixir_captures = false;
    matching_conf = Match_patterns.default_matching_conf;
    matching_explanations = false;
    (* TODO: set to true by default?
     * Anyway it's set to true in Runner_config.default so it will default to
     * true when running as part of the regular code path (not testing code)
     *)
    filter_irrelevant_rules = NoPrefiltering;
  }

let needs_legacy_elixir_captures (rule : Rule.t) (target : Xtarget.t) =
  let found =
    ref (List.exists (Lang.equal Lang.Elixir) (Xlang.to_langs target.xlang))
  in
  Rule.formulas_of_mode rule.mode
  |> List.iter
       (Visit_rule.visit_formula (fun formula ->
            List.iter
              (function
                | _, Rule.CondNestedFormula (_, Some lang, _) ->
                    if
                      List.exists (Lang.equal Lang.Elixir) (Xlang.to_langs lang)
                    then found := true
                | _ -> ())
              formula.Rule.conditions));
  !found

let merge_legacy_results modern legacy =
  let open Core_result in
  if
    not
      (Core_error.ErrorSet.is_empty
         (Core_error.ErrorSet.diff legacy.errors modern.errors))
  then
    raise
      (Core_error.Unhandled_core_error
         (Core_error.mk_error
            ~msg:
              "Legacy fingerprint matching failed; scan aborted to preserve \
               finding identities"
            FatalError));
  let site (m : Core_match.t) =
    let start, end_ = m.range_loc in
    ( m.rule_id.id,
      m.path,
      start.pos.bytepos,
      end_.pos.bytepos,
      String.length end_.str )
  in
  let legacy_sites = Hashtbl.create (List.length legacy.matches) in
  List.iter (fun m -> Hashtbl.replace legacy_sites (site m) ()) legacy.matches;
  let matches =
    legacy.matches
    @ List.filter
        (fun m -> not (Hashtbl.mem legacy_sites (site m)))
        modern.matches
    |> Core_match.uniq
  in
  let profiling =
    match (modern.profiling, legacy.profiling) with
    | Some a, Some b ->
        Some
          {
            a with
            Core_profiling.rule_match_time =
              a.Core_profiling.rule_match_time
              +. b.Core_profiling.rule_match_time;
          }
    | (Some _ as p), _
    | _, (Some _ as p) ->
        p
    | None, None -> None
  in
  { modern with matches; profiling }
