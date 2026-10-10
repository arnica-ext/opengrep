open Common
module MV = Metavariable
module OutJ = Semgrep_output_v1_j
module OutUtils = Semgrep_output_utils
module G = AST_generic

(*****************************************************************************)
(* Prelude *)
(*****************************************************************************)

(*****************************************************************************)
(* Types *)
(*****************************************************************************)

type replacement = {
  mval_content : string Lazy.t;
  propagated_content : string option;
}

type replacement_ctx = (string * replacement) list

(*****************************************************************************)
(* Helpers *)
(*****************************************************************************)

let string_of_any tokens_of_any any =
  (* TODO: metavar_string_of_any is used in get_propagated_value
      to get the string for propagated values. Not all propagated
      values will have origintoks. For example, in
          x = 1; y = x + 1; ...
     we have y = 2 but there is no source location for 2.
     Handle such cases *)
  (* FIXME: If the match is a variable, extract the variable, not the
     propagated value / definition assigned by name resolution. This is a
     temporary fix for the nondeterministic behaviour bug (issue #335) *)
  match any with
  | G.E { e_range = Some (l1, l2); _ } when Int.equal l1.pos.bytepos l2.pos.bytepos ->
      l1.str
  | _ ->
      any |> tokens_of_any
      |> List.filter Tok.is_origintok
      |> List.sort Tok.compare_pos
      |> List_.map Tok.content_of_tok
      |> Core_text_output.join_with_space_if_needed

let metavar_string_of_any any = string_of_any AST_generic_helpers.ii_of_any any

(* Keep the 1.15 token representation separate from the analysis AST. *)
let legacy_tokens lang any =
  let remaining = ref 20_000_000 in
  let visitor =
    object (self)
      inherit [_] AST_generic_helpers.reporting_visitor as super

      method! visit_tok tokens tok =
        decr remaining;
        if !remaining < 0 then
          failwith
            "Legacy fingerprint capture exceeds 20,000,000 token visits; scan aborted to preserve finding identities";
        super#visit_tok tokens tok

      method! visit_expr tokens expr =
        match (expr.G.e_original, lang, expr.e) with
        | Some _, _, _ -> super#visit_expr tokens expr
        | ( None,
            Some (Lang.Js | Lang.Ts),
            G.Constructor (G.Id (("...", tok), _), _) ) ->
            self#visit_tok tokens tok
        | ( None,
            Some Lang.Ruby,
            G.ArrayAccess
              (base, (lb, { e = G.Container (G.Array, (_, args, _)); _ }, rb)) )
          ->
            self#visit_expr tokens base;
            List.iter (self#visit_tok tokens) [ lb; lb; lb ];
            List.iter (self#visit_expr tokens) args;
            self#visit_tok tokens rb
        | None, Some Lang.Csharp, G.ArrayAccess (base, (lb, index, rb)) ->
            self#visit_expr tokens base;
            self#visit_tok tokens lb;
            (match index.e with
            | G.Container (G.Tuple, _) -> self#visit_expr tokens index
            | _ ->
                self#visit_tok tokens lb;
                self#visit_expr tokens index;
                self#visit_tok tokens rb);
            self#visit_tok tokens rb
        | None, Some Lang.Elixir, G.OtherExpr (("PipelineCall", _), [ G.E call ])
          ->
            self#visit_expr tokens call
        | None, Some Lang.Java, G.OtherExpr (("MethodRef", tok), first :: rest)
          ->
            self#visit_tok tokens tok;
            self#visit_any tokens first;
            List.iter
              (function
                | G.Ta _ -> ()
                | part -> self#visit_any tokens part)
              rest
        | None, Some Lang.Java, G.LetPattern (G.PatTyped (G.PatId _, ty), value)
          ->
            self#visit_expr tokens value;
            self#visit_type_ tokens ty
        | ( None,
            Some Lang.Dart,
            G.New (tok, { t = G.TyApply (ty, _); _ }, _, args) )
          when Tok.is_fake tok ->
            self#visit_type_ tokens ty;
            self#visit_arguments tokens args
        | _ -> super#visit_expr tokens expr

      method! visit_literal tokens literal =
        match (lang, literal) with
        | Some Lang.Elixir, G.Atom (colon, (_, name))
          when Tok.is_origintok colon && Tok.is_origintok name
               && Int.equal (Tok.compare_pos colon name) 0 ->
            self#visit_tok tokens name
        | _ -> super#visit_literal tokens literal

      method! visit_function_definition tokens def =
        match (lang, def.G.fkind) with
        | Some (Lang.Rust | Lang.Dart | Lang.Julia), (G.LambdaKind, _) ->
            self#visit_parameters tokens def.fparams;
            Option.iter (self#visit_type_ tokens) def.frettype;
            self#visit_function_body tokens def.fbody
        | _ -> super#visit_function_definition tokens def

      method! visit_parameter tokens param =
        match (lang, param) with
        | Some Lang.Rust, G.ParamPattern (pat, classic) ->
            super#visit_parameter tokens
              (G.ParamPattern (pat, { classic with pattrs = [] }))
        | _ -> super#visit_parameter tokens param

      method! visit_pattern tokens pat =
        match (lang, pat) with
        | Some (Lang.Js | Lang.Ts), G.PatConstructor (G.Id (("...", tok), _), _)
          ->
            self#visit_tok tokens tok
        | Some Lang.Clojure, G.PatKeyVal (key, value) ->
            self#visit_pattern tokens value;
            self#visit_pattern tokens key
        | _ -> super#visit_pattern tokens pat
    end
  in
  let tokens = ref [] in
  visitor#visit_any tokens any;
  List.rev !tokens

let rec original_for_reporting = function
  | G.E { e_original = Some original; _ } ->
      original_for_reporting original
  | any -> any

let metavar_abstract_content ?lang any =
  string_of_any (legacy_tokens lang) (original_for_reporting any)

let propagated_value_string_of_mval ?lang ~for_reporting mval =
  let any = MV.mvalue_to_any mval in
  match any with
  | G.E { e = N (Id (_, id_info)); _ } -> (
      let svalue =
        match !(id_info.id_svalue) with
        | None when for_reporting -> !(id_info.id_legacy_svalue)
        | Some (Sym expr)
          when for_reporting
               && not (Dataflow_svalue.is_symbolic_expr ~legacy:true expr) ->
            !(id_info.id_legacy_svalue)
        | value -> value
      in
      match svalue with
      | Some (Lit x) ->
          let any = G.E (G.L x |> G.e) in
          Some (metavar_string_of_any any)
      | Some (Sym x) ->
          let any = G.E x in
          Some
            (if for_reporting then metavar_abstract_content ?lang any
             else metavar_string_of_any any)
      | Some (Cst _) -> None
      | Some NotCst -> None
      | None -> None)
  | __else__ -> None

(*****************************************************************************)
(* Entry points *)
(*****************************************************************************)

let of_bindings ?(for_reporting = false) ?(metavar_lang = fun _ -> None) bindings =
  bindings
  |> List_.filter_map (fun (mvar, mval) ->
      let ranged_mval =
        if for_reporting then
          mval |> MV.mvalue_to_any |> original_for_reporting |> MV.mvalue_of_any
        else mval
      in
      match MV.range_of_mvalue ranged_mval with
      | None -> None
      | Some (file, mval_range) ->
          let mval_content = lazy (Range.content_at_range file mval_range) in
          let propagated_content =
            propagated_value_string_of_mval ?lang:(metavar_lang mvar)
              ~for_reporting ranged_mval
          in
          Some (mvar, { mval_content; propagated_content }))

let of_out (metavars : OutJ.metavars) =
  metavars
  |> List_.map (fun (mvar, metavar_value) ->
         let mval_content = lazy metavar_value.OutJ.abstract_content in
         let propagated_content =
           Option.map
             (fun svalue -> svalue.OutJ.svalue_abstract_content)
             metavar_value.propagated_value
         in
         (mvar, { mval_content; propagated_content }))

let interpolate_metavars (text : string) (ctx : replacement_ctx) : string =
  (* sort by metavariable length to avoid name collisions
   * (eg. $X2 must be handled before $X)
   *)
  let ctx =
    ctx
    |> List.sort (fun (a, _) (b, _) ->
           compare (String.length b) (String.length a))
  in
  ctx
  |> List.fold_left
       (fun text (mvar, { mval_content; propagated_content }) ->
         (* necessary typing to help the type check disambiguate fields,
          * because of the use of multiple fields with the same
          * name in semgrep_output_v1.atd *)

         (* first value($X), and then $X *)
         text
         |> Str.global_substitute
              (Str.regexp_string (spf "value(%s)" mvar))
              (fun _whole_str ->
                match propagated_content with
                | Some s -> s (* default to the matched value *)
                | None -> Lazy.force mval_content)
         |> Str.global_substitute (Str.regexp_string mvar) (fun _whole_str ->
                Lazy.force mval_content))
       text
