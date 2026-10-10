defmodule Probe do
  def run() do
    a = %User{data: source(), name: "safe"}
    sink(a)
    sink(a.data)
    sink(a.name)
  end
end
