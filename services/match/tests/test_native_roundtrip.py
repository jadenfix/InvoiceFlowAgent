"""Actual PostgreSQL and RabbitMQ roundtrip; no mocked provider in this lane."""
import json
from decimal import Decimal
from urllib.parse import quote
import pytest
from sqlalchemy import select
from app.core.config import settings
from app.models.invoice import Invoice
from app.services import matching_service as matching_module
from app.services.message_queue import MessageQueueService


@pytest.mark.asyncio
@pytest.mark.parametrize('amount,expected', [('990.00', 'AUTO_APPROVED'), ('1500.00', 'NEEDS_REVIEW')])
async def test_actual_match_persist_publish_consume(
    matching_service, db_service, db_session, sample_purchase_order,
    rabbitmq_container, monkeypatch, amount, expected,
):
    params = rabbitmq_container.get_connection_params()
    user = quote(params.credentials.username, safe='')
    password = quote(params.credentials.password, safe='')
    monkeypatch.setattr(settings, 'rabbitmq_url', f'amqp://{user}:{password}@{params.host}:{params.port}/')
    queue = MessageQueueService()
    await queue.initialize()
    monkeypatch.setattr(matching_module, 'mq_service', queue)
    request_id = 'native-match-' + expected.lower()
    try:
        invoice = Invoice(request_id=request_id, total_amount=Decimal(amount), po_numbers=['PO123456'])
        db_session.add(invoice)
        await db_session.commit()
        await matching_service.process_invoice_extracted_message({
            'request_id': request_id, 'raw_key': 'explicit-fixture/invoice.pdf',
            'fields': {'total_amount': amount, 'po_numbers':['PO123456']},
        })
        notification = await queue.queues['invoice_matched'].get(timeout=5, no_ack=True)
        assert notification is not None
        body = json.loads(notification.body)
        assert body['request_id'] == request_id and body['status'] == expected
        assert Decimal(body['details']['invoice_amount']) == Decimal(amount)
        assert body['details']['po_number'] == 'PO123456'
        assert notification.delivery_mode.value == 2
        async with db_service.get_session() as session:
            saved = await session.scalar(select(Invoice).where(Invoice.request_id == request_id))
            assert saved.matched_status == expected
            assert saved.matched_at is not None
            assert Decimal(saved.matched_details['invoice_amount']) == Decimal(amount)
        assert await db_service.health_check() and await queue.health_check()
    finally:
        await queue.close()
