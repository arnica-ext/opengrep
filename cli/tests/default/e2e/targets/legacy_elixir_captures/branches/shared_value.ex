defmodule Probe do
  def run(flag) do
    a = %User{}
    b = if flag, do: a, else: a
    sink(b)
  end
end
