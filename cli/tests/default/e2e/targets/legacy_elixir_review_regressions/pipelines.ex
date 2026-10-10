defmodule Probe do
 def pipeline_alias(x) do
  b = wrap(x |> f())
  sink(b)
 end
 def plain_alias(x) do
  b = wrap(f(x))
  sink(b)
 end
 def inline_pipeline(x) do
  sink(wrap(x |> f()))
 end
 def inline_direct(x) do
  sink(wrap(f(x)))
 end
 def tainted_pipeline() do
  source() |> f() |> danger()
 end
end
