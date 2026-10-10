# Preserve offsets outside the nested capture.

a = wrap(source())
a[0] = clean()
sink(a)
