# The Caddy release of this base image and the SHA-256 of its LICENSE at that tag. The
# release workflow refuses another version or license text (notices, W4-7, S83-2).
# Change this line together with the FROM line.
# caddy-license: v2.10.2 cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30
FROM caddy@sha256:4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d

RUN setcap -r /usr/bin/caddy \
    && chown -R 1000:1000 /config /data

USER 1000:1000

ENTRYPOINT ["caddy"]
CMD ["run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
