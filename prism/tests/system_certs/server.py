#!/usr/bin/python3

import ssl
from http.server import HTTPServer, SimpleHTTPRequestHandler


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        data = b"Hello world\n"
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


httpd = HTTPServer(("localhost", 12345), Handler)
sslctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
sslctx.check_hostname = False
sslctx.load_cert_chain(certfile="testserver.crt", keyfile="testserver.key")
httpd.socket = sslctx.wrap_socket(httpd.socket, server_side=True)
httpd.serve_forever()
