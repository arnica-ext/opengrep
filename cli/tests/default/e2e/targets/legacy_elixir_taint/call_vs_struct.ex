defmodule Probe do
  def run() do
    a = %User{}
    sink(a)
    sink(%User{})
  end
end
