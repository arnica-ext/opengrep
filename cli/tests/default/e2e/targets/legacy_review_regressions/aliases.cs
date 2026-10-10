class C {
  void F() {
    var a = source[0];
    sink(a);
    sink(a);
    sink(source[0]);
    var b = source?[0];
    sink(b);
    sink(source?[0]);
    var c = source[0, 1];
    sink(c);
    sink(source[0, 1]);
  }
}
