defmodule Probe do
  def run() do
    a = source()
    b = %User{}
    transfer(a, b, %User{})
    sink(b)
  end
end
