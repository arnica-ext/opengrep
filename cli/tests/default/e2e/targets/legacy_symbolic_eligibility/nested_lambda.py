a = wrap(lambda: source())
a.attr = clean()
sink(a)
