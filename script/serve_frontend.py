"""No-cache dev server for frontend/"""
import http.server
import sys

class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def log_message(self, *args):
        pass  # silent

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    import os
    os.chdir("frontend")
    httpd = http.server.HTTPServer(("", port), NoCacheHandler)
    print(f"Frontend serving on http://localhost:{port}")
    httpd.serve_forever()
