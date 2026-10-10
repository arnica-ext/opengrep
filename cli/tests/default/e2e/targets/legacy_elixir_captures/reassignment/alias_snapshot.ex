a = %User{}
b = a
a = "safe"
sink(a)
sink(b)
