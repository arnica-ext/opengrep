a = %User{}
sink(a)
sink(%User{})
sink(a, a)
sink(a, %User{})
sink(%User{}, a)
sink(a, %Admin{})
