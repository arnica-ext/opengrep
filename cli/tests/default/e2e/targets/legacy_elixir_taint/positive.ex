defmodule Probe do
  def run() do
    a = source()
    sink(a)
  end
end
