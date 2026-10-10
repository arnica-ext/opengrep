fun f(a: Thing) { sink(a.let { x -> f(x) }.let { y -> g(y) }); }
