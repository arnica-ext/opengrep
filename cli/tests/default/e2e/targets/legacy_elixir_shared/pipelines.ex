defmodule Pipelines do
  def plain(value) do
    sink(wrap(value |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f()))
  end

  def capture() do
    sink(wrap(&(&1 |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f())))
  end

  def long_capture() do
    sink(wrap(&(&1 |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f())))
  end

  def branches(value) do
    sink(wrap(case value do
      {:ok, x} -> x |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f() |> f()
    end))
  end
end
