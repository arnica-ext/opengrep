const https = require("https");
function object_default({value = eval(userInput)} = {}) { return value; }
function array_default([value = eval(userInput)] = []) { return value; }
function whole_default({value} = {value: eval(userInput)}) { return value; }
const arrow_default = ({value = eval(userInput)} = {}) => value;
function nested_default({inner: {value = eval(userInput)}}) { return value; }
function tls_nested({options = {rejectUnauthorized: false}} = {}) {
  return https.request("https://example.com", options);
}
function tls_whole({options} = {options: {rejectUnauthorized: false}}) {
  return https.request("https://example.com", options);
}
function tls_binding({rejectUnauthorized = false} = {}) {
  return https.request("https://example.com", {rejectUnauthorized});
}
