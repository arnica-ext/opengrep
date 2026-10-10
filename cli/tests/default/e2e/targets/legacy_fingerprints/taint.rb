def interpolate
  render inline: "<div>#{params[:name]}</div>"
end

def format
  render inline: "<div>%s</div>" % params[:name]
end

def env_interpolate
  render inline: "<div>#{request.env['METHOD']}</div>"
end

def env_format
  render inline: "<div>%s</div>" % request.env['METHOD']
end
