FROM alpine
COPY --link src dst
ADD --link src dst
COPY --parents src dst
COPY --chown=user src dst
