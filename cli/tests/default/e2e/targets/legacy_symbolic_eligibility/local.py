def f():
    a = [source()]
    sink(a)
    a[0] = clean()
    sink(a)
