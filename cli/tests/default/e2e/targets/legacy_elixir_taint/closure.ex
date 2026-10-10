defmodule Probe do
  def run(items) do
    a = source()
    Enum.each(items, fn _ -> sink(a) end)
  end
end
