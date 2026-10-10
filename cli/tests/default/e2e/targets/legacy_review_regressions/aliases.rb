a = params[:x]
sink(a)
b = params["y"]
sink(b)
c = params[:x, :y]
sink(c)
d = params[:x][:y]
sink(d)
e = params[[:x]]
sink(e)
f = [:x]
sink(f)
g = -> { 1 }
sink(g)
h = receiver.foo
sink(h)
i = receiver.foo()
sink(i)
