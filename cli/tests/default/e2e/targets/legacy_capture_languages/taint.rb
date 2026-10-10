def test
  value = source("eval(args[0]);")
  sink(value, params[:name])
end
