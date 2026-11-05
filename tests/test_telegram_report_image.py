from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image

from src.notification_sender.telegram_sender import TelegramSender
from src.notification import NotificationChannel, NotificationService


def png(width, height):
    output = BytesIO()
    Image.new("RGBA", (width, height), (255, 255, 255, 255)).save(output, "PNG", compress_level=0)
    return output.getvalue()


def test_short_report_is_sent_as_photo():
    sender = TelegramSender(SimpleNamespace(telegram_bot_token="token", telegram_chat_id="chat", telegram_message_thread_id="7"))
    with patch("src.notification_sender.telegram_sender.requests.post") as post:
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"ok": True}
        assert sender._send_telegram_photo(png(400, 500))
    args, kwargs = post.call_args
    assert args[0].endswith("/sendPhoto")
    assert kwargs["data"] == {"chat_id": "chat", "message_thread_id": "7"}
    assert "photo" in kwargs["files"]


def test_long_report_is_compressed_and_sent_as_one_document():
    sender = TelegramSender(SimpleNamespace(telegram_bot_token="token", telegram_chat_id="chat"))
    original = png(400, 10000)
    with patch("src.notification_sender.telegram_sender.requests.post") as post:
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"ok": True}
        assert sender._send_telegram_photo(original)
    args, kwargs = post.call_args
    assert args[0].endswith("/sendDocument")
    sent = kwargs["files"]["document"][1]
    assert len(sent) < len(original)
    with Image.open(BytesIO(sent)) as image:
        assert image.size == (400, 10000)


def test_unreadable_image_fails_without_sending():
    sender = TelegramSender(SimpleNamespace(telegram_bot_token="token", telegram_chat_id="chat"))
    with patch("src.notification_sender.telegram_sender.requests.post") as post:
        assert not sender._send_telegram_photo(b"not an image")
    post.assert_not_called()


def test_static_telegram_route_falls_back_to_text_when_image_fails():
    service = NotificationService.__new__(NotificationService)
    service._markdown_to_image_channels = {"telegram"}
    service._send_telegram_photo = Mock(return_value=False)
    service.send_to_telegram = Mock(return_value=True)
    assert service._send_to_static_channel(
        NotificationChannel.TELEGRAM, "report", image_bytes=b"png",
        email_stock_codes=None, email_send_to_all=False,
    )
    service.send_to_telegram.assert_called_once_with("report")
