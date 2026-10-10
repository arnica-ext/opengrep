sink("hello #{name}")
sink(%{a: 1})
sink(%Thing{a: 1})
sink(fn x -> x + 1 end)
sink(x |> foo() |> bar())
sink(case x do
  {:ok, y} -> y
  _ -> nil
end)
