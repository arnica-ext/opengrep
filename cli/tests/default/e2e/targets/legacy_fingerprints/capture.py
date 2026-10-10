import flask
app = flask.Flask(__name__)
app.config["WTF_CSRF_ENABLED"] = False
app.config.update(WTF_CSRF_ENABLED=False)
app.config.update(WTF_CSRF_ENABLED=False)
other = flask.Flask("other")
other = replacement()
other.config.update(WTF_CSRF_ENABLED=False)
