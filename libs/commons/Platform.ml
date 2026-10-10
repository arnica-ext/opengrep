(* TODO: other options for Windows! *)
type arch = Arm | Arm64 | X86_64 | OtherArch of string
type kernel = Darwin | Linux | OtherKernel of string

let arch (caps : < Cap.exec >) =
  let output =
    match CapExec.string_of_run caps#exec ~trim:true (Cmd.Name "uname", [ "-m" ]) with
    | Ok (output, _status) -> output
    | Error (`Msg _) -> ""
  in
  let s = String.lowercase_ascii output in
  match s with
  | "arm" -> Arm
  | "arm64" -> Arm64
  | "x86_64" -> X86_64
  | _ -> OtherArch s

let kernel (caps : < Cap.exec >) =
  let output =
    match CapExec.string_of_run caps#exec ~trim:true (Cmd.Name "uname", []) with
    | Ok (output, _status) -> output
    | Error (`Msg _) -> ""
  in
  let s = String.lowercase_ascii output in
  match s with
  | "darwin" -> Darwin
  | "linux" -> Linux
  | _ -> OtherKernel s

(* TODO? || Sys.cygwin? *)
let is_windows = Sys.win32
