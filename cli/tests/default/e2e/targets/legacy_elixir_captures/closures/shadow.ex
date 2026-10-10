defmodule Probe do
  def run(items) do
    a = %User{}
    Enum.each(items, fn a -> sink(a) end)
    sink(a)
  end
end
