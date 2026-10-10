defmodule Probe do
  def run() do
    sink(%User{data: source()})
  end
end
