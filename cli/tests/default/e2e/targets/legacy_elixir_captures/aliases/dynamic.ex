defmodule Probe do
  def run(module) do
    a = %module{}
    sink(a)
  end
end
