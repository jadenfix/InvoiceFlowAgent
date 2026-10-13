"""Password compatibility, secret-safe validation and lifecycle regressions."""
from datetime import datetime, timezone
import pytest
from unittest.mock import Mock
from app.models.user import User
from app.core.config import settings, Settings
from app.core.rate_limiter import check_user_account_lockout
from fastapi import HTTPException
from app import main


def test_bcrypt_legacy_hash_and_byte_limit():
    user = User(hashed_password='$2b$12$.myxi5/hnqD5UacakpMeR.3puOZ7s1.lNRpa4QoH35cpdDsiVZcs.')
    assert user.verify_password('TestPassword123')
    assert not user.verify_password('wrong')
    user.set_password('A1' + 'x' * 70)
    assert user.verify_password('A1' + 'x' * 70)
    assert not user.verify_password('A1' + 'x' * 71)
    with pytest.raises(ValueError, match='72 UTF-8 bytes'):
        user.set_password('A1' + 'é' * 36)


def test_invalid_password_is_not_echoed(test_client):
    secret = 'S' * 73 + 'ecret123'
    response = test_client.post('/auth/register', json={'email':'fixture@example.com', 'password':secret})
    assert response.status_code == 422
    assert secret not in response.text and '72 UTF-8 bytes' in response.text


def test_aware_postgres_lockout_timestamps():
    user = User(email='locked@example.com', failed_login_attempts=settings.rate_limit_attempts, last_failed_login=datetime.now(timezone.utc))
    assert user.is_account_locked()
    with pytest.raises(HTTPException) as error:
        check_user_account_lockout(user)
    assert error.value.status_code == 423


@pytest.mark.asyncio
async def test_lifespan_closes_dependencies_after_body_failure(monkeypatch):
    close = Mock()
    monkeypatch.setattr(main, 'init_db', lambda: True)
    monkeypatch.setattr(main, 'close_db', close)
    with pytest.raises(RuntimeError, match='application fault fixture'):
        async with main.lifespan(main.app):
            raise RuntimeError('application fault fixture')
    close.assert_called_once()


def test_constructor_production_requires_explicit_credentials(monkeypatch):
    monkeypatch.delenv('JWT_SECRET', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    with pytest.raises(ValueError):
        Settings(environment='production', jwt_secret=None, database_url=None)
