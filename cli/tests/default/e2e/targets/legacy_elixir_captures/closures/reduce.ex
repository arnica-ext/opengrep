defmodule Probe do
  def run(items) do
    a = Enum.reduce(items, %User{}, fn _item, acc ->
      sink(acc)
      acc
    end)
    sink(a)
  end
end
