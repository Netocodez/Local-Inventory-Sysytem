from waitress import serve
from app import app  # or whatever your app filename/module is

if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=8080)