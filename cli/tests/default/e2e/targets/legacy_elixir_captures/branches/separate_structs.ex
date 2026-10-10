defmodule Probe do
  def run(flag) do
    a = if flag, do: %User{}, else: %User{}
    sink(a)
  end
end
