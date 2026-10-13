"""Real HTTP/PostgreSQL auth gate. Requires the configured PostgreSQL service."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy import create_engine, text


def main():
    if not __debug__:
        raise RuntimeError("Native checks require assertions enabled")
    created = False
    database_url = os.environ['DATABASE_URL']
    if not database_url.startswith('postgresql://'):
        raise ValueError('This native gate requires actual PostgreSQL')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    email = f'native-{uuid.uuid4().hex}@example.com'
    password = 'NativeFixturePassword123'
    env = dict(os.environ, LOG_LEVEL='WARNING')
    engine = create_engine(database_url)
    with tempfile.TemporaryFile(mode='w+') as log:
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)], env=env, stdout=log, stderr=subprocess.STDOUT)
        def http(method, path, payload=None, token=None):
            headers = {'Content-Type':'application/json'}
            if token:
                headers['Authorization'] = 'Bearer ' + token
            request = Request(base + path, data=json.dumps(payload).encode() if payload is not None else None, headers=headers, method=method)
            try:
                with urlopen(request, timeout=5) as response:
                    return response.status, json.load(response)
            except HTTPError as response:
                return response.code, json.load(response)
        try:
            deadline = time.monotonic() + 50
            while True:
                if process.poll() is not None:
                    raise RuntimeError('Auth process exited before readiness')
                try:
                    ready_status, ready = http('GET', '/readyz')
                    if ready_status == 200 and ready['checks']['database']['status'] == 'healthy':
                        break
                except (URLError, TimeoutError, ConnectionError):
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError('Actual PostgreSQL-backed Auth never became ready')
                time.sleep(0.1)
            data = {'email':email, 'password':password, 'full_name':'Native Auth Fixture'}
            status, registered = http('POST', '/auth/register', data)
            assert status == 201 and registered['email'] == email
            created = True
            assert 'hashed_password' not in registered and 'password' not in registered
            status, login = http('POST', '/auth/login', {'email':email, 'password':password})
            assert status == 200 and login['token_type'] == 'bearer'
            status, me = http('GET', '/auth/me', token=login['access_token'])
            assert status == 200 and me['id'] == registered['id']
            assert http('GET', '/auth/me', token='invalid.fixture.token')[0] == 401
            assert http('POST', '/auth/register', data)[0] == 409
            secret = 'LongSecretPassword123' * 5
            status, invalid = http('POST', '/auth/register', dict(data, password=secret))
            assert status == 422 and secret not in json.dumps(invalid)
            with engine.connect() as connection:
                persisted = connection.execute(text('SELECT email, hashed_password FROM users WHERE email=:email'), {'email':email}).one()
                assert persisted.email == email and persisted.hashed_password.startswith('$2b$')
            print(json.dumps({'status':'passed', 'providers':'actual subprocess HTTP and PostgreSQL', 'checks':['readiness actual DB', 'signup persisted bcrypt hash', 'login JWT', 'authenticated me', 'invalid JWT denied', 'duplicate denied', 'secret-safe validation'], 'fixture':'generated account; no mocked provider'}))
        except BaseException:
            log.seek(0)
            print(log.read()[-12000:], file=sys.stderr)
            raise
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            try:
                if created:
                    with engine.begin() as connection:
                        connection.execute(text('DELETE FROM users WHERE email=:email'), {'email':email})
            finally:
                engine.dispose()


if __name__ == '__main__':
    main()
