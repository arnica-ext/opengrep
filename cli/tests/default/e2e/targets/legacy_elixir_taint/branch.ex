defmodule Probe do
  def run(flag) do
    a = if flag, do: source(), else: "safe"
    sink(a)
  end
end
