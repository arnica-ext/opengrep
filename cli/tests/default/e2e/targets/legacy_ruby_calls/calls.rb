receiver.foo
receiver.foo()
receiver.foo(value)
receiver.foo { |x| sink(x) }
receiver.foo(value) { |x| sink(x) }
receiver.foo do |x|
  sink(x)
end
