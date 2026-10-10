defmodule Probe do
  def run(items) do
    a = %User{}
    Enum.each(items, fn _item -> sink(a) end)
    sink(a)
  end
end
