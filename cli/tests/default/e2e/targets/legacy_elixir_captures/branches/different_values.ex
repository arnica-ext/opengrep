defmodule Probe do
  def run(flag) do
    a = if flag, do: %User{}, else: "safe"
    sink(a)
  end
end
