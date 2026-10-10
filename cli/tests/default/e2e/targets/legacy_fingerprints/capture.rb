sink(params[:id])
sink(<<~SQL)
  SELECT * FROM t WHERE id = #{params[:id]}
SQL
sink(Digest::SHA1.hexdigest(value))
sink(Digest::SHA1.hexdigest)
sink(Digest::SHA1.hexdigest(value))
config = { :secret => "value", :secret_other => "other", :not_secret => "ignored" }
