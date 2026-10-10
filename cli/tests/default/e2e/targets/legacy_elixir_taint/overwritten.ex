defmodule Probe do
  def run() do
    a = source()
    a = %User{}
    sink(a)
  end
end
