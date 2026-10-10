defmodule Probe do
  def run(flag) do
    a = case flag do
      true -> %User{}
      _ -> "safe"
    end
    sink(a)
  end
end
