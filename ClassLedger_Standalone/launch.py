import os,socket,webbrowser
from app import create_app
from waitress import serve
port=int(os.environ.get('PORT','8000'))
app=create_app()
print(f'\nOpen on this computer: http://localhost:{port}')
try:
    ips=socket.gethostbyname_ex(socket.gethostname())[2]
    for ip in ips:
        if not ip.startswith('127.'):
            print(f'Possible same-Wi-Fi address: http://{ip}:{port}')
except OSError:pass
print('Set the correct Wi-Fi address in Settings before downloading a QR.')
print('Keep this window open while students use the app. Ctrl+C stops the server.\n')
webbrowser.open(f'http://localhost:{port}')
serve(app,host='0.0.0.0',port=port)
