function shorthand({ value = true, other }) {
  return value;
}

function renamed({ value: local = true, other }) {
  return local;
}

function nested({ outer: { value = true }, other }) {
  return value;
}

function plain({ value, other }) {
  return value;
}

function rest({ value, ...other }) { return value; }
function defaultRest({ value = true, ...other }) { return value; }
function defaultObject({ value = {foo: true}, other }) { return value; }
function defaultArray({ value = [true, false], other }) { return value; }
function defaultCall({ value = fallback(), other }) { return value; }
function defaultVar({ value = fallback, other }) { return value; }
function nestedRename({ outer: { value: local = true }, other }) { return local; }
function aliasObject({ value: local = {foo: true}, other }) { return local; }
function computed({ [key]: value, other }) { return value; }
function array([value = true, other]) { return value; }
function allDefault({value = true, other = false}) { return value; }
function outerDefault({value = true, other} = {}) { return value; }
function outerRest({value, ...other} = {}) { return value; }

function repeated({ value = true, ...other }) {}
function repeated({ value = true, ...other }) {}

function nestedFunction({ value = function inner({ enabled = true, ...rest }) {} }) {}
function typed({ value = true, ...rest }: Options) {}

function nestedCapture({ outer: { value = true, other } }) { return value; }
